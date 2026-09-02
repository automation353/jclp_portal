from rest_framework import serializers

from .models import RawMaterial


class RawMaterialSerializer(serializers.ModelSerializer):
    """Ships the stored policy columns plus the derived buy decision, so the
    front end never has to re-implement the reorder rule."""

    to_purchase = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    needs_purchase = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = RawMaterial
        fields = [
            "id",
            "name",
            "on_hand",
            "reorder_level",
            "reorder_qty",
            "to_purchase",
            "needs_purchase",
            "status",
        ]


class EBQRequestSerializer(serializers.Serializer):
    annual_demand = serializers.FloatField()
    ordering_cost = serializers.FloatField()
    holding_cost = serializers.FloatField()


class UserSerializer(serializers.Serializer):
    username = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    role = serializers.CharField()
    role_display = serializers.SerializerMethodField()
    department = serializers.CharField()
    is_super_admin = serializers.BooleanField()

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_role_display(self, obj):
        return obj.get_role_display()
