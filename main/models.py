from django.db import models
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import User
from accounts.models import TkdBoard
from django.utils import timezone
class HeaderBackground(models.Model):
    background_image = models.ImageField(
        upload_to='header_backgrounds/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        help_text="عکس بک‌گراند هدر"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Header Background {self.id}"

    class Meta:
        verbose_name = "بک گراند هدر"
        verbose_name_plural = " بک گراند های هدر"
class SliderImage(models.Model):
    image = models.ImageField(
        upload_to='slider_images/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        verbose_name="عکس اسلایدر"
    )
    title = models.CharField(max_length=100, blank=True, null=True, verbose_name="عنوان")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = "عکس اسلایدر"
        verbose_name_plural = "عکس‌های اسلایدر"

    def __str__(self):
        return f"Slider Image {self.id}"


class News(models.Model):
    title = models.CharField(max_length=200, verbose_name="عنوان")
    content = models.TextField(verbose_name="محتوای خبر")
    image = models.ImageField(
        upload_to='news_images/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        verbose_name="عکس"
    )
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="نویسنده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    board = models.ForeignKey(TkdBoard, null=True, blank=True, on_delete=models.SET_NULL, related_name='news')
    published = models.BooleanField(default=False, verbose_name="منتشر شده؟")
    class Meta:
        ordering = ['-created_at']
        verbose_name = "خبر"
        verbose_name_plural = "اخبار"

    def __str__(self):
        return self.title


class Circular(models.Model):
    title = models.CharField(max_length=200, verbose_name="عنوان")
    content = models.TextField(verbose_name="محتوای بخش‌نامه")
    thumbnail = models.ImageField(
        upload_to='circular_thumbnails/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        verbose_name="عکس شاخص"
    )
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="منتشرکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ انتشار")
    published = models.BooleanField(default=False, verbose_name="منتشر شده؟")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "بخش‌نامه"
        verbose_name_plural = "بخش‌نامه‌ها"

    def __str__(self):
        return self.title


class CircularImage(models.Model):
    circular = models.ForeignKey(Circular, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='circular_images/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        verbose_name="عکس الحاقی"
    )

    def __str__(self):
        return f"عکس برای {self.circular.title}"


class CircularAttachment(models.Model):
    circular = models.ForeignKey(Circular, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(
        upload_to='circular_attachments/',
        validators=[FileExtensionValidator(['pdf'])],
        verbose_name="فایل PDF"
    )

    def __str__(self):
        return f"فایل برای {self.circular.title}"

class NewsImage(models.Model):
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='news_images/multiple/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        verbose_name="عکس الحاقی"
    )

    def __str__(self):
        return f"عکس برای {self.news.title}"
