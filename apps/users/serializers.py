from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "phone", "farm_name"]

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data.pop("password")
        return User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=User.FARMER,
            phone=validated_data.get("phone", ""),
            farm_name=validated_data.get("farm_name", ""),
        )


class RegisterAppManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "phone", "first_name", "last_name"]

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data.pop("password")
        return User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=User.APP_MANAGER,
            phone=validated_data.get("phone", ""),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data["email"], password=data["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        data["user"] = user
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "email", "role",
            "phone", "farm_name", "language",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "role", "date_joined"]
