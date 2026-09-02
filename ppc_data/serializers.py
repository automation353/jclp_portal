from rest_framework import serializers

from .models import PPCDemandFreeze, PPCDemandTransaction, PPCUploadBatch


class PPCUploadBatchSerializer(serializers.ModelSerializer):
    uploader = serializers.StringRelatedField()

    class Meta:
        model = PPCUploadBatch
        fields = [
            "id", "uploader", "uploaded_at", "source_file",
            "original_filename", "file_type", "level", "table_key",
            "row_count", "is_current", "parse_error", "notes",
        ]


class PPCDemandFreezeSerializer(serializers.ModelSerializer):
    frozen_by = serializers.StringRelatedField()

    class Meta:
        model = PPCDemandFreeze
        fields = [
            "id", "item_code", "month", "initial_qty",
            "frozen_at", "frozen_by",
        ]


class PPCDemandTransactionSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()

    class Meta:
        model = PPCDemandTransaction
        fields = [
            "id", "freeze", "tx_type", "qty", "week",
            "reason", "created_at", "created_by",
        ]
