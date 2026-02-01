import React, { useEffect, useState } from 'react';
import Slider from 'react-slick';
import { Link } from 'react-router-dom';
import './CircularSlider.css';
import "slick-carousel/slick/slick.css";
import "slick-carousel/slick/slick-theme.css";

const CircularSlider = () => {
  const [circulars, setCirculars] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('https://api.chbtkd.ir/api/circulars/slider/')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setCirculars(data);
        else setCirculars([]);
        setLoading(false);
      })
      .catch(err => {
        console.error("❌ خطا در دریافت اطلاعیه‌ها:", err);
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
    fade: false,          
    cssEase: 'linear',
    adaptiveHeight: true,
  };

  return (
    <div className="circular-slider-wrapper">
      <h4>اطلاعیه و بخشنامه</h4>

      {loading ? (
        <p>در حال بارگذاری...</p>
      ) : circulars.length > 0 ? (
        <Slider {...settings}>
          {circulars.map((item) => (
            <div key={item.id} className="circular-slide">
              <Link to={`/circular/${item.id}`} className="circular-link">
                {item.thumbnail_url && (
                  <img
                    src={item.thumbnail_url}
                    alt={item.title || "Circular"}
                    className="circular-image"
                    loading="lazy"
                  />
                )}
                <div className="circular-caption">
                  <h3>{item.title}</h3>
                </div>
              </Link>
            </div>
          ))}
        </Slider>
      ) : (
        <p>اطلاعیه‌ای یافت نشد.</p>
      )}
    </div>
  );
};

export default CircularSlider;
