from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .showcase_models import Lecturer, LecturerAppearance, CampActivity


class ShowcaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        appearances = LecturerAppearance.objects.filter(state="published", published_at__isnull=False).exclude(confirmation_status="declined").select_related("lecturer", "edition")
        def serialize(appearance):
            lecturer = appearance.lecturer
            return {"id": appearance.pk, "name": lecturer.name, "designation": lecturer.designation,
                    "biography": lecturer.biography, "alt_text": lecturer.alt_text,
                    "edition": {"id": appearance.edition_id, "name": appearance.edition.name},
                    "topic": appearance.topic if appearance.participation_type == "upcoming" or appearance.verified else "",
                    "confirmed": appearance.verified, "featured": appearance.featured,
                    "image_url": reverse("dic:showcase-image", args=["lecturer", appearance.pk])}
        previous = appearances.filter(participation_type="previous")
        edition = request.query_params.get("edition")
        if edition:
            if not edition.isascii() or not edition.isdigit() or len(edition) > 9:
                return Response({"detail": "Invalid edition filter."}, status=400)
            previous = previous.filter(edition_id=int(edition))
        activities = CampActivity.objects.filter(state="published", published_at__isnull=False, edition__year=2026).select_related("edition")
        data = {"upcoming": [serialize(item) for item in appearances.filter(participation_type="upcoming", edition__year=2026)[:100]],
                "previous": [serialize(item) for item in previous[:200]],
                "activities": [{"id": item.pk, "title": item.title, "description": item.description,
                                "category": item.category, "featured": item.featured, "alt_text": item.alt_text,
                                "image_url": reverse("dic:showcase-image", args=["activity", item.pk]) if item.photograph else None} for item in activities[:200]]}
        response = Response(data)
        response["Cache-Control"] = "no-store"
        return response


def showcase_image(request, kind, pk):
    if request.method != "GET":
        raise Http404
    if kind == "identity":
        if not (request.user.is_active and request.user.is_staff and request.user.has_perm("dic.view_lecturer")):
            raise Http404
        obj = get_object_or_404(Lecturer, pk=pk)
        photograph = obj.photograph
    elif kind in ("lecturer", "activity"):
        model = LecturerAppearance if kind == "lecturer" else CampActivity
        query = model.objects.all()
        if request.GET.get("preview") == "1":
            if not (request.user.is_active and request.user.is_staff and request.user.has_perm(f"dic.view_{model._meta.model_name}")):
                raise Http404
        else:
            query = query.filter(state="published", published_at__isnull=False)
            if kind == "lecturer":
                query = query.exclude(confirmation_status="declined")
        obj = get_object_or_404(query, pk=pk)
        photograph = obj.lecturer.photograph if kind == "lecturer" else obj.photograph
    else:
        raise Http404
    if not photograph:
        raise Http404
    response = FileResponse(photograph.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="dic-showcase.jpg"'
    return response
