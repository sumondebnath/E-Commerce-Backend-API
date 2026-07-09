from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import password_validation
from .models import Address

User = get_user_model()

class AddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = Address
        fields = ["id","address_type", "street_address", "city", "state", "postal_code", "country", "is_default", "created_at"]
        read_only_fields = ["id", "created_at"]

        def create(self, validated_data):
            validated_data["user"] = self.context["request"].user
            return super().create(validated_data)
        

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "roles", "is_active", "addresses", "created_at"]
        read_only_fields = ["id", "is_active", "created_at"]

    def get_roles(self, obj):
        if obj.is_superuser:
            return ["admin"]
        if obj.is_staff:
            return ["staff"]
        return ["user"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label="Confirm Password")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "password", "password2"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()
    
    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user
        

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct.")
        return value
    
    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password": "New password fields didn't match."})
        password_validation.validate_password(attrs["new_password"], self.context["request"].user)
        return attrs
    
    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["full_name"] = user.full_name
        token["is_staff"] = user.is_staff
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = UserSerializer(self.user).data
        return data
    
    