from django.core.exceptions import ValidationError
from django.http import Http404, FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .memory_models import CampVideo
from .video_providers import video_source


def public_video(pk):
    video = get_object_or_404(CampVideo, pk=pk, state="published", published_at__isnull=False)
    try:
        video_source(video.video_url)
    except ValidationError:
        raise Http404 from None
    return video


class VideosView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        videos = CampVideo.objects.filter(state="published", published_at__isnull=False).select_related("edition").prefetch_related("activities")
        for parameter, field in (("edition", "edition_id"), ("activity", "activities__id")):
            value = request.query_params.get(parameter)
            if value:
                if not value.isascii() or not value.isdigit() or len(value) > 9:
                    return Response({"detail": "Invalid video filter."}, status=400)
                videos = videos.filter(**{field: int(value)})
        data = []
        for video in videos.distinct()[:200]:
            try:
                source = video_source(video.video_url)
            except ValidationError:
                continue  # Revoked providers disappear immediately, even before content edits.
            data.append({"id": video.pk, "caption": video.caption, "alt_text": video.alt_text,
                         "edition": {"id": video.edition_id, "name": video.edition.name},
                         "activities": [{"id": tag.pk, "name": tag.name} for tag in video.activities.all()],
                         "featured": video.featured, "provider": source["provider"],
                         "thumbnail_url": reverse("dic:video-thumbnail", args=[video.pk]),
                         "playback_url": reverse("dic:video-playback", args=[video.pk])})
        response = Response({"videos": data})
        response["Cache-Control"] = "no-store"
        return response


class VideoPlaybackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, pk):
        video = public_video(pk)
        response = Response(video_source(video.video_url))
        response["Cache-Control"] = "private, no-store"
        return response


def video_thumbnail(request, pk):
    if request.method != "GET":
        raise Http404
    if request.GET.get("preview") == "1":
        if not request.user.is_active or not request.user.is_staff or not request.user.has_perm("dic.view_campvideo"):
            raise Http404
        video = get_object_or_404(CampVideo, pk=pk)
    else:
        video = public_video(pk)
    response = FileResponse(video.thumbnail.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = 'inline; filename="camp-video-thumbnail.jpg"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
