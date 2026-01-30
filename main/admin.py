from django.contrib import admin
from .models import HeaderBackground , SliderImage , News , Circular, CircularImage ,CircularAttachment,NewsImage

@admin.register(HeaderBackground)
class HeaderBackgroundAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at',)
    readonly_fields = ('created_at',)


@admin.register(SliderImage)
class SliderImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'order')
    ordering = ['order']
    fields = ('image', 'title', 'order')

class NewsImageInline(admin.TabularInline):
    model = NewsImage
    extra = 1

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at', 'published')
    list_editable = ('published',)
    list_filter = ('published',)
    search_fields = ('title', 'content')
    inlines = [NewsImageInline]
    readonly_fields = ('created_at',)


class CircularImageInline(admin.TabularInline):
    model = CircularImage
    extra = 1


class CircularAttachmentInline(admin.TabularInline):
    model = CircularAttachment
    extra = 1
@admin.register(Circular)
class CircularAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at', 'published')
    list_editable = ('published',)
    readonly_fields = ('created_at',)
    inlines = [CircularImageInline, CircularAttachmentInline]
    fieldsets = (
        (None, {'fields': ('title', 'content', 'thumbnail')}),
        ('وضعیت انتشار', {'fields': ('published',)}),
        ('نویسنده و زمان', {'fields': ('author', 'created_at')}),
    )


@admin.register(CircularImage)
class CircularImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'circular', 'image')