from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from .memory_models import CampPhotograph


class MemoriesView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        photos = CampPhotograph.objects.filter(state="published", published_at__isnull=False).select_related("edition").prefetch_related("activities")
        for parameter, field in (("edition", "edition_id"), ("activity", "activities__id")):
            value = request.query_params.get(parameter)
            if value:
                if not value.isascii() or not value.isdigit() or len(value) > 9:
                    return Response({"detail": "Invalid gallery filter."}, status=400)
                photos = photos.filter(**{field: int(value)})
        # Bounded gallery. No draft-derived edition or activity metadata is exposed.
        data = [{"id": photo.pk, "edition": {"id": photo.edition_id, "name": photo.edition.name},
                 "activities": [{"id": tag.pk, "name": tag.name} for tag in photo.activities.all()],
                 "caption": photo.caption, "alt_text": photo.alt_text, "featured": photo.featured,
                 "image_url": reverse("dic:memory-image", args=[photo.pk])} for photo in photos.distinct()[:200]]
        response = Response({"photographs": data})
        response["Cache-Control"] = "no-store"
        return response


def memory_image(request, pk):
    if request.method != "GET":
        raise Http404
    photos = CampPhotograph.objects.all()
    if request.GET.get("preview") == "1":
        if not request.user.is_active or not request.user.is_staff or not request.user.has_perm("dic.view_campphotograph"):
            raise Http404
    else:
        photos = photos.filter(state="published", published_at__isnull=False)
    photo = get_object_or_404(photos, pk=pk)
    response = FileResponse(photo.photograph.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="camp-memory.jpg"'
    return response
