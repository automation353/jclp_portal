from rest_framework import serializers

from .models import PurchasePlanningUpload


class PurchasePlanningUploadSerializer(serializers.ModelSerializer):
    uploader_username = serializers.CharField(source="uploader.username", read_only=True)
    uploader_department = serializers.CharField(source="uploader.department", read_only=True)

    class Meta:
        model = PurchasePlanningUpload
        fields = [
            "id",
            "original_filename",
            "uploaded_at",
            "uploader_username",
            "uploader_department",
            "notes",
        ]
