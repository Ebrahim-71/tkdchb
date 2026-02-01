import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import "./NewsCard.css"; // استایل مخصوص کارت خبر

const NewsCard = ({ news }) => {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const getSnippet = () => {
    const plainText = news.content?.replace(/<[^>]+>/g, "") || "";
    const limit = isMobile ? 20 : 60;
    return plainText.length > limit
      ? `${plainText.slice(0, limit)}...`
      : plainText;
  };

  const imageSrc = news.image?.startsWith("http")
    ? news.image
    : `https://api.chbtkd.ir${news.image}`;

  return (
    <div className="news-card">
      <img
        src={imageSrc}
        alt="تصویر خبر"
        className="news-image"
        onError={(e) => (e.target.src = "/placeholder.jpg")}
      />

      <h3 className="news-title">{news.title}</h3>

      <p className="news-snippet">{getSnippet()}</p>

      <div className="news-meta">
        <span>
          {new Date(news.created_at).toLocaleDateString("fa-IR")} | منتشرکننده:{" "}
          {news.author_name}
        </span>
      </div>

      <Link to={`/news/${news.id}`} className="news-button">
        جزئیات بیشتر
      </Link>
    </div>
  );
};

export default NewsCard;
