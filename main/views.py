from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from .models import HeaderBackground , SliderImage , News,Circular,NewsImage
from .serializers import HeaderBackgroundSerializer , SliderImageSerializer ,NewsSerializer ,CircularSerializer,BoardNewsSubmitSerializer

class HeaderBackgroundAPIView(APIView):
    def get(self, request):
        try:
            # آخرین بک‌گراند را برمی‌گردانیم
            background = HeaderBackground.objects.latest('created_at')
            serializer = HeaderBackgroundSerializer(background)
            return Response(serializer.data)
        except HeaderBackground.DoesNotExist:
            return Response({"background_image": ""}, status=200)



class SliderImagesAPIView(APIView):
    def get(self, request):
        images = SliderImage.objects.all()
        serializer = SliderImageSerializer(images, many=True)
        return Response(serializer.data)

# views.py

class NewsSliderAPIView(APIView):
    """چهار خبر آخر برای اسلایدر صفحه اصلی"""
    def get(self, request):
        news_items = News.objects.filter(published=True).order_by('-created_at')[:4]
        serializer = NewsSerializer(news_items, many=True)
        return Response(serializer.data)


class NewsListAPIView(APIView):
    """لیست کامل اخبار منتشر شده برای داشبورد"""
    def get(self, request):
        news_items = News.objects.filter(published=True).order_by('-created_at')
        serializer = NewsSerializer(news_items, many=True)
        return Response(serializer.data)


class NewsDetailView(APIView):
    def get(self, request, pk):
        try:
            news = News.objects.get(id=pk, published=True)
            serializer = NewsSerializer(news)
            return Response(serializer.data)
        except News.DoesNotExist:
            return Response({"error": "این خبر وجود ندارد"}, status=404)

class CircularListAPIView(APIView):
    def get(self, request):
        circulars = Circular.objects.filter(published=True).order_by('-created_at')[:4]
        serializer = CircularSerializer(circulars, many=True, context={'request': request})
        return Response(serializer.data)

class CircularsListAPIView(APIView):
    def get(self, request):
        circulars = Circular.objects.filter(published=True).order_by('-created_at')
        serializer = CircularSerializer(circulars, many=True, context={'request': request})
        return Response(serializer.data)



class CircularDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            circular = Circular.objects.get(id=pk, published=True)
            serializer = CircularSerializer(circular, context={'request': request})
            return Response(serializer.data)
        except Circular.DoesNotExist:
            return Response({"error": "این بخش‌نامه وجود ندارد"}, status=404)





class SendOTPView(APIView):
    def post(self, request):
        phone = request.data.get('phone')
        if not phone:
            return Response({'error': 'شماره موبایل الزامی است'}, status=400)

        code = str(random.randint(1000, 9999))
        MobileOTP.objects.update_or_create(
            phone_number=phone,
            defaults={'code': code, 'is_verified': False}
        )

        # اینجا پیامک واقعی ارسال نمی‌کنیم فعلا
        print(f"کد تایید: {code}")
        return Response({'message': 'کد ارسال شد'}, status=200)




class BoardNewsSubmitAPIView(generics.CreateAPIView):
    serializer_class = BoardNewsSubmitSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]  # چون فرم شامل فایل‌ هست

    def perform_create(self, serializer):
        user = self.request.user
        if not hasattr(user, 'tkdboard'):
            raise PermissionDenied('دسترسی فقط برای هیئت مجاز است.')

        # فقط صدا زدن save() کافی است
        news = serializer.save()  # ✅ بدون پارامتر اضافی

        # ذخیره تصاویر الحاقی
        for image in self.request.FILES.getlist('images'):
            NewsImage.objects.create(news=news, image=image)


class BoardMyNewsListAPIView(generics.ListAPIView):
    serializer_class = BoardNewsSubmitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not hasattr(self.request.user, 'tkdboard'):
            return News.objects.none()
        return News.objects.filter(board=self.request.user.tkdboard).order_by('-id')