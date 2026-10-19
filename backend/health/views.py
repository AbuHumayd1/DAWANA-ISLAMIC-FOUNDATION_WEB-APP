from django.db import connection, DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            response = Response({"status": "unavailable"}, status=503)
        else:
            response = Response({"status": "ok"})
        response["Cache-Control"] = "no-store"
        return response
