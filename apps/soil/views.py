from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from apps.utils.email_translate import translate_email_content
from .services import analyze_soil_image, NotSoilImageError


class SoilAnalysisView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if "image" not in request.FILES:
            return Response(
                {"error": "An image file is required. Send it as multipart/form-data with key 'image'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        image_file = request.FILES["image"]

        if not image_file.content_type.startswith("image/"):
            return Response(
                {"error": "Uploaded file must be an image."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = analyze_soil_image(image_file.read(), language=request.user.language)
        except NotSoilImageError as e:
            message = translate_email_content(str(e), request.user.language, is_html=False)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Soil analysis failed: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result)
