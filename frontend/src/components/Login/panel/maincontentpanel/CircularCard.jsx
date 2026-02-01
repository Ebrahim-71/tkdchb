import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import "./CircularCard.css";

const CircularCard = ({ circular }) => {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const getContentSnippet = () => {
    const plainText = circular.content?.replace(/<[^>]+>/g, "") || "";
    const limit = isMobile ? 20 : 60;
    return plainText.length > limit ? `${plainText.slice(0, limit)}...` : plainText;
  };

  return (
    <div className="circular-card">
      {/* عکس شاخص */}
      <img
        src={circular.thumbnail_url || "/placeholder.jpg"}
        alt="عکس شاخص"
        className="circularimage"
        onError={(e) => (e.target.src = "/placeholder.jpg")}
      />

      {/* عنوان */}
      <h3>{circular.title}</h3>

      {/* توضیح کوتاه */}
      <p>{getContentSnippet()}</p>

      {/* اطلاعات متا */}
      <div className="circular-meta">
        <span>
          {circular.has_attachments ? "دارای فایل ضمیمه" : "بدون فایل ضمیمه"}
        </span>
        <span>
          {new Date(circular.created_at).toLocaleDateString("fa-IR")} | منتشرکننده:{" "}
          {circular.author_name}
        </span>
      </div>

      {/* دکمه جزئیات */}
      <Link to={`/circular/${circular.id}`} className="details-button">
        جزئیات بیشتر
      </Link>
    </div>
  );
};

export default CircularCard;
