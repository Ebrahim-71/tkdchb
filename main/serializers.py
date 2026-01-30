from rest_framework import serializers
from .models import HeaderBackground , SliderImage,News ,Circular, CircularImage,CircularAttachment,News,NewsImage

class HeaderBackgroundSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeaderBackground
        fields = ['background_image']


class SliderImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SliderImage
        fields = ['image', 'title']

class NewsImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsImage
        fields = ['image']

class NewsSerializer(serializers.ModelSerializer):
    images = NewsImageSerializer(many=True, read_only=True)  # 👈 اضافه شود

    class Meta:
        model = News
        fields = ['id', 'title', 'content', 'image', 'author', 'created_at', 'images']


class CircularAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CircularAttachment
        fields = ['file']
class CircularImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CircularImage
        fields = ['image']
class CircularSerializer(serializers.ModelSerializer):
    author_username = serializers.SerializerMethodField()
    admin_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    has_attachments = serializers.SerializerMethodField()
    images = CircularImageSerializer(many=True, read_only=True)
    attachments = CircularAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Circular
        fields = [
            'id', 'title', 'thumbnail', 'thumbnail_url', 'content',
            'images', 'attachments', 'author_username', 'admin_name',
            'has_attachments', 'created_at', 'published'
        ]

    def get_author_username(self, obj):
        return obj.author.username if obj.author else "ناشناس"

    def get_admin_name(self, obj):
        return obj.author.get_full_name() if obj.author else "نامشخص"

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail and hasattr(obj.thumbnail, 'url'):
            return request.build_absolute_uri(obj.thumbnail.url)
        return ""

    def get_has_attachments(self, obj):
        return obj.attachments.exists()


class BoardNewsSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = News
        fields = ['id', 'title', 'content', 'image']
        read_only_fields = ['id']

    def create(self, validated_data):
        request = self.context['request']

        # ساخت خبر
        news = News.objects.create(
            **validated_data,
            author=request.user,
            board=getattr(request.user, 'tkdboard', None),
            published=False
        )

        # ذخیره‌ی عکس‌های الحاقی
        images = request.FILES.getlist('images')  # ← عکس‌ها از فرم
        for image in images:
            NewsImage.objects.create(news=news, image=image)

        return news