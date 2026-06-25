from django.db.models import Count
from django.utils import timezone
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.users.models import User
from apps.history.models import AnalysisRecord
from apps.history.serializers import AnalysisRecordSerializer


class DashboardPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_privileged


class StatsView(APIView):
    permission_classes = [DashboardPermission]

    def get(self, request):
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)

        return Response({
            "farmers": {
                "total": User.objects.filter(role=User.FARMER).count(),
                "new_last_7_days": User.objects.filter(role=User.FARMER, date_joined__gte=last_7_days).count(),
                "new_last_30_days": User.objects.filter(role=User.FARMER, date_joined__gte=last_30_days).count(),
            },
            "analyses": {
                "total": AnalysisRecord.objects.count(),
                "last_7_days": AnalysisRecord.objects.filter(created_at__gte=last_7_days).count(),
                "last_30_days": AnalysisRecord.objects.filter(created_at__gte=last_30_days).count(),
            },
        })


class FarmerListView(APIView):
    permission_classes = [DashboardPermission]

    def get(self, request):
        farmers = (
            User.objects.filter(role=User.FARMER)
            .annotate(analysis_count=Count("analyses"))
            .order_by("-date_joined")
            .values("id", "email", "phone", "farm_name", "date_joined", "analysis_count")
        )
        return Response(list(farmers))


class FarmerDetailView(APIView):
    permission_classes = [DashboardPermission]

    def get(self, request, pk):
        try:
            farmer = User.objects.get(pk=pk, role=User.FARMER)
        except User.DoesNotExist:
            return Response({"error": "Farmer not found."}, status=status.HTTP_404_NOT_FOUND)

        analyses = AnalysisRecord.objects.filter(farmer=farmer)
        return Response({
            "id": farmer.id,
            "email": farmer.email,
            "phone": farmer.phone,
            "farm_name": farmer.farm_name,
            "date_joined": farmer.date_joined,
            "analysis_count": analyses.count(),
            "recent_analyses": AnalysisRecordSerializer(analyses[:10], many=True).data,
        })
