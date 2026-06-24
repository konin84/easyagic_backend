from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "password", "phone", "farm_name", "farm_latitude", "farm_longitude"]

    def create(self, validated_data):
        email = validated_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            role=User.FARMER,
            phone=validated_data.get("phone", ""),
            farm_name=validated_data.get("farm_name", ""),
            farm_latitude=validated_data.get("farm_latitude"),
            farm_longitude=validated_data.get("farm_longitude"),
        )
        return user


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
            "phone", "farm_name", "farm_latitude", "farm_longitude",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "role", "date_joined"]
