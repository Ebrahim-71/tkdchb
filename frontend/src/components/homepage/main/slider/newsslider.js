import React, { useEffect, useState } from 'react';
import Slider from 'react-slick';
import { Link } from 'react-router-dom';
import './NewsSlider.css';
import "slick-carousel/slick/slick.css";
import "slick-carousel/slick/slick-theme.css";

const NewsSlider = () => {
  const [newsList, setNewsList] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('https://api.chbtkd.ir/api/news/slider/')
      .then(res => res.json())
      .then(data => {
        setNewsList(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(err => {
        console.error("❌ خطا در دریافت اخبار:", err);
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
    fade: false, // ← بهتره برای چند آیتم خاموش باشه
  };

  return (
    <div className="news-slider-wrapper">
      <h4>اخبار استان و شهرستان</h4>

      {loading ? (
        <p>در حال بارگذاری...</p>
      ) : newsList.length > 0 ? (
        <Slider {...settings}>
          {newsList.map((news) => (
            <div key={news.id} className="news-slide">
              <Link to={`/news/${news.id}`} className="news-link">
                {news.image && (
                  <img
                    src={`https://api.chbtkd.ir${news.image}`}
                    alt={news.title || "خبر"}
                    className="newsimage"
                    loading="lazy"
                  />
                )}
                <div className="news-caption">
                  <h3>{news.title}</h3>
                </div>
              </Link>
            </div>
          ))}
        </Slider>
      ) : (
        <p>هیچ خبری یافت نشد.</p>
      )}
    </div>
  );
};

export default NewsSlider;
