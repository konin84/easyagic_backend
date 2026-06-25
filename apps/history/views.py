from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import AnalysisRecord
from .serializers import AnalysisRecordSerializer


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = AnalysisRecord.objects.filter(farmer=request.user)
        serializer = AnalysisRecordSerializer(records, many=True)
        return Response(serializer.data)


class AnalysisRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            record = AnalysisRecord.objects.get(pk=pk, farmer=request.user)
        except AnalysisRecord.DoesNotExist:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AnalysisRecordSerializer(record).data)
