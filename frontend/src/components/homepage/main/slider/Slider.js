import React, { useEffect, useState } from 'react';
import Slider from 'react-slick';
import './Slider.css';
import "slick-carousel/slick/slick.css";
import "slick-carousel/slick/slick-theme.css";

const API_BASE = "https://api.chbtkd.ir";

const ImageSlider = () => {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/slider-images/`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setImages(data);
        } else {
          setImages([]);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error("❌ خطا در دریافت API:", err);
        setLoading(false);
      });
  }, []);

  const settings = {
    dots: true,
    infinite: true,
    speed: 500,
    slidesToShow: 1,
    slidesToScroll: 1,
    autoplay: true,
    autoplaySpeed: 3000,
    arrows: true,
    cssEase: 'linear',
    adaptiveHeight: true,
    fade: false,
    appendDots: dots => (
      <div>
        <ul style={{ margin: 0 }}>{dots}</ul>
      </div>
    ),
    customPaging: i => (
      <div
        style={{
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          background: '#bbb',
          display: 'inline-block',
          margin: '-20px',
        }}
      />
    )
  };

  return (
    <div className="slider-wrapper">
      <h4>گالری تصاویر</h4>

      {loading ? (
        <p>در حال بارگذاری تصاویر...</p>
      ) : images.length > 0 ? (
        <Slider {...settings}>
          {images.map((image, index) => (
            <div key={index} className="slide">
              {image.image && (
                <img
                  src={`${API_BASE}${image.image}`}
                  alt={image.title || `اسلایدر ${index + 1}`}
                  className="slider-image"
                  loading="lazy"
                />
              )}
              {image.title && <div className="slider-caption">{image.title}</div>}
            </div>
          ))}
        </Slider>
      ) : (
        <p>هیچ عکسی برای اسلایدر وجود ندارد</p>
      )}
    </div>
  );
};

export default ImageSlider;
