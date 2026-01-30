from django.urls import path
from .views import (
    HeaderBackgroundAPIView,
    SliderImagesAPIView,
    NewsSliderAPIView,  # اضافه شده
    NewsListAPIView,  # اضافه شده
    NewsDetailView,
    CircularListAPIView,
    CircularsListAPIView,
    CircularDetailAPIView,
    BoardNewsSubmitAPIView,
    BoardMyNewsListAPIView
)

urlpatterns = [
    path('header-background/', HeaderBackgroundAPIView.as_view(), name='header-background'),
    path('slider-images/', SliderImagesAPIView.as_view(), name='slider-images'),
    path('news/slider/', NewsSliderAPIView.as_view(), name='news-slider'),  # فقط ۴ خبر
    path('news/', NewsListAPIView.as_view(), name='news-list'),  # همه اخبار
    path('news/<int:pk>/', NewsDetailView.as_view(), name='news-detail'),
    path('circulars/slider/', CircularListAPIView.as_view(), name='circulars-slider'),
    path('circulars/', CircularsListAPIView.as_view(), name='circulars'),
    path('circulars/<int:pk>/', CircularDetailAPIView.as_view(), name='circular-detail'),
    path('news/board/submit/', BoardNewsSubmitAPIView.as_view(), name='board-news-submit'),
    path('news/board/mine/', BoardMyNewsListAPIView.as_view(), name='board-news-mine'),
]
