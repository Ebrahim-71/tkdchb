import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AdvancedLightbox from './AdvancedLightbox'; // مسیرت رو تنظیم کن
import './CircularDetail.css';

const NewsDetail = () => {
  const { id } = useParams();
  const [news, setNews] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`/api/news/${id}/`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setNews(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("خطا در دریافت جزئیات خبر:", err);
        setLoading(false);
      });
  }, [id]);

  if (loading) return <p>در حال بارگذاری...</p>;
  if (!news) return <p>این خبر یافت نشد.</p>;

  const fullImages = news.images?.map(img =>
    img.image.startsWith("http") ? img.image : `${img.image}`
  ) || [];

  return (
    <div className="circular-detail-page">
      <h1>{news.title}</h1>

      <div className="back-to-home">
        <button onClick={() => navigate(-1)} className="back-button">
          ← بازگشت به صفحه قبل
        </button>
      </div>

      {/* تصویر شاخص */}
      {news.image && (
        <img
          src={`https://api.chbtkd.ir/${news.image}`}
          alt={news.title}
          className="thumbnail"
        />
      )}

      {/* متن خبر */}
      <p className="content-text" style={{ whiteSpace: 'pre-line', direction: 'rtl', textAlign: 'right' }}>
        {news.content}
      </p>

      {/* تصاویر الحاقی */}
      {fullImages.length > 0 && (
        <div className="extra-images">
          <h4>تصاویر بیشتر:</h4>
          <div className="images-gallery">
            {fullImages.map((src, i) => (
              <img
                key={i}
                src={src}
                alt={`پیوست ${i + 1}`}
                className="zoomable-image"
                onClick={() => {
                  setSelectedIndex(i);
                  setLightboxOpen(true);
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* لایت‌باکس */}
      {lightboxOpen && (
        <AdvancedLightbox
          images={fullImages}
          initialIndex={selectedIndex}
          onClose={() => setLightboxOpen(false)}
        />
      )}

      {/* متا */}
      <div className="meta-info">
        <p>نویسنده: {news.author_name}</p>
        <p>تاریخ انتشار: {new Date(news.created_at).toLocaleString('fa-IR')}</p>
      </div>
    </div>
  );

};

export default NewsDetail;
