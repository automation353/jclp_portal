"""Serializers for the Super Admin panel API."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from portal.data import DEPARTMENTS

from .models import LoginEvent, UserModuleAccess

User = get_user_model()


class ModuleSerializer(serializers.Serializer):
    """Read-only representation of a portal module (from portal.data)."""

    slug = serializers.CharField()
    name = serializers.CharField()
    icon = serializers.CharField()
    description = serializers.CharField()
    is_open = serializers.BooleanField()


class UserModuleAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserModuleAccess
        fields = ("module_slug", "granted_at")


class UserListSerializer(serializers.ModelSerializer):
    """Compact user representation for the team table."""

    modules = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "first_name", "last_name", "email",
            "role", "department", "is_active", "date_joined",
            "last_login", "modules",
        )

    def get_modules(self, obj):
        if obj.role == User.Role.SUPER_ADMIN:
            return [d["slug"] for d in DEPARTMENTS]
        return list(
            obj.module_access.values_list("module_slug", flat=True)
        )


class UserDetailSerializer(serializers.ModelSerializer):
    """Full user representation for create/edit."""

    modules = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
    )
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "first_name", "last_name", "email",
            "role", "department", "is_active", "password", "modules",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The ListField handles writes; on read we pull the actual grants.
        if instance.role == User.Role.SUPER_ADMIN:
            data["modules"] = [d["slug"] for d in DEPARTMENTS]
        else:
            data["modules"] = list(
                instance.module_access.values_list("module_slug", flat=True)
            )
        return data

    def validate_modules(self, value):
        valid_slugs = {d["slug"] for d in DEPARTMENTS}
        bad = [s for s in value if s not in valid_slugs]
        if bad:
            raise serializers.ValidationError(
                f"Unknown module slug(s): {', '.join(bad)}"
            )
        return value

    def create(self, validated_data):
        modules = validated_data.pop("modules", [])
        password = validated_data.pop("password", "")
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        self._sync_modules(user, modules)
        return user

    def update(self, instance, validated_data):
        modules = validated_data.pop("modules", None)
        password = validated_data.pop("password", "")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if modules is not None:
            self._sync_modules(instance, modules)
        return instance

    def _sync_modules(self, user, slugs):
        granted_by = self.context.get("request")
        granted_by = granted_by.user if granted_by else None

        existing = set(
            user.module_access.values_list("module_slug", flat=True)
        )
        wanted = set(slugs)

        # Remove revoked
        user.module_access.filter(module_slug__in=existing - wanted).delete()

        # Add new grants
        UserModuleAccess.objects.bulk_create(
            [
                UserModuleAccess(
                    user=user, module_slug=s, granted_by=granted_by,
                )
                for s in wanted - existing
            ],
            ignore_conflicts=True,
        )


class LoginEventSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = LoginEvent
        fields = ("id", "username", "full_name", "event_type", "timestamp", "ip_address")

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
