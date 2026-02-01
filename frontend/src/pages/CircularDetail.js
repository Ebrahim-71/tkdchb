import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AdvancedLightbox from './AdvancedLightbox'; // مسیرت رو تنظیم کن
import pdf_icon from '../assets/icons/pdf-icon.png';
import './CircularDetail.css';

const CircularDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [circular, setCircular] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    fetch(`/api/circulars/${id}/`)
      .then(res => res.json())
      .then(data => {
        if (!data.error) setCircular(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("خطا در دریافت جزئیات:", err);
        setLoading(false);
      });
  }, [id]);

  if (loading) return <p>در حال بارگذاری...</p>;
  if (!circular) return <p>این اطلاعیه یافت نشد.</p>;

  const images = circular.images || [];
  const pdfAttachments = circular.attachments || [];

  // ساخت URLهای کامل برای تصاویر الحاقی
  const fullImages = images.map(img =>
    img.image.startsWith('http') ? img.image : `${img.image}`
  );

  return (
    <div className="circular-detail-page">
      <h1>{circular.title}</h1>

      {/* دکمه بازگشت */}
      <div className="back-to-home">
        <button onClick={() => navigate(-1)} className="back-button">
          ← بازگشت به صفحه قبل
        </button>
      </div>

      {/* تصویر شاخص */}
      {circular.thumbnail_url && (
        <img
          src={circular.thumbnail_url}
          alt={circular.title}
          className="thumbnail"
        />
      )}

      {/* محتوای متن */}
      <p className="content-text" style={{ whiteSpace: 'pre-line', direction: 'rtl', textAlign: 'right' }}>
        {circular.content}
      </p>

      {/* تصاویر الحاقی با قابلیت باز شدن در لایت‌باکس */}
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

      {/* لایت‌باکس با زوم */}
      {lightboxOpen && (
        <AdvancedLightbox
          images={fullImages}
          initialIndex={selectedIndex}
          onClose={() => setLightboxOpen(false)}
        />
      )}

      {/* فایل‌های PDF */}
      {pdfAttachments.length > 0 && (
        <div>
          <h4>فایل‌های پیوست:</h4>
          <div className="pdf-attachments">
            {pdfAttachments.map((att, i) => (
              <a
                key={i}
                href={att.file.startsWith('http') ? att.file : `https://api.chbtkd.ir${att.file}`}
                target="_blank"
                rel="noopener noreferrer"
                title={`دانلود فایل ${i + 1}`}
              >
                <img src={pdf_icon} alt={`PDF ${i + 1}`} />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* اطلاعات متا */}
      <div className="meta-info">
        <p>منتشرکننده: {circular.author_name}</p>

        <p>تاریخ انتشار: {new Date(circular.created_at).toLocaleString('fa-IR')}</p>
      </div>
    </div>
  );
};

export default CircularDetail;
