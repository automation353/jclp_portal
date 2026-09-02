from rest_framework import serializers

from .models import (
    MtoMtsChange,
    MtoMtsEmailLog,
    MtoMtsItem,
    MtoMtsNotification,
    MtoMtsUpload,
)


class MtoMtsCellSerializer(serializers.Serializer):
    month_label = serializers.CharField()
    month_index = serializers.IntegerField()
    value = serializers.CharField(allow_blank=True)


class MtoMtsItemSerializer(serializers.ModelSerializer):
    cells = MtoMtsCellSerializer(many=True, read_only=True)

    class Meta:
        model = MtoMtsItem
        fields = [
            "id",
            "item_group",
            "item_code",
            "segment",
            "account_description",
            "system_suggested",
            "trend_tag",
            "current_month_status",
            "last_edited_by_dept",
            "sales_reason",
            "ops_reason",
            "sales_status",   # kept for Phase 3/4
            "ops_status",     # kept for Phase 3/4
            "cells",
        ]


class MtoMtsUploadSerializer(serializers.ModelSerializer):
    uploader_username = serializers.CharField(source="uploader.username", read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = MtoMtsUpload
        fields = [
            "id",
            "original_filename",
            "month_label",
            "uploaded_at",
            "status",
            "lock_at",
            "locked_at",
            "validation_notes",
            "uploader_username",
            "item_count",
        ]

    def get_item_count(self, obj):
        return obj.items.count()


class MtoMtsChangeSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.item_code", read_only=True)
    item_group = serializers.CharField(source="item.item_group", read_only=True)
    changed_by_username = serializers.CharField(source="changed_by.username", read_only=True)
    field_display = serializers.CharField(source="get_field_display", read_only=True)

    class Meta:
        model = MtoMtsChange
        fields = [
            "id",
            "item_code",
            "item_group",
            "field",
            "field_display",
            "old_value",
            "new_value",
            "comment",
            "changed_by_username",
            "department",
            "changed_at",
        ]


class MtoMtsNotificationSerializer(serializers.ModelSerializer):
    change = MtoMtsChangeSerializer(read_only=True)

    class Meta:
        model = MtoMtsNotification
        fields = ["id", "change", "seen_at", "created_at"]


class MtoMtsEmailLogSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = MtoMtsEmailLog
        fields = [
            "id", "kind", "kind_display", "subject", "recipients",
            "body_preview", "sent_at", "delivered",
            "upload", "change",
        ]
