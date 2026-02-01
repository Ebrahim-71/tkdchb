import React, { useState } from "react";
import axios from "axios";
import "../dashboard.css";

const HeyatCreateNews = () => {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [image, setImage] = useState(null); // تصویر شاخص
  const [images, setImages] = useState([]); // تصاویر الحاقی
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const token = localStorage.getItem("heyat_token");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr("");
    setMsg("");

    if (!title.trim() || !content.trim() || !image) {
      setErr("عنوان، متن و تصویر شاخص الزامی است.");
      return;
    }

    const form = new FormData();
    form.append("title", title.trim());
    form.append("content", content.trim());
    form.append("image", image); // عکس شاخص

    images.forEach((img) => {
      form.append("images", img); // عکس‌های الحاقی
    });

    try {
      setSubmitting(true);
      await axios.post(
        "https://api.chbtkd.ir/api/news/board/submit/",
        form,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "multipart/form-data",
          },
        }
      );
      setMsg("خبر ثبت شد و برای تأیید ادمین ارسال گردید.");
      setTitle("");
      setContent("");
      setImage(null);
      setImages([]);
      document.getElementById("main-image").value = "";
      document.getElementById("extra-images").value = "";
    } catch (e) {
      setErr("خطا در ثبت خبر.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="item-card" style={{ maxWidth: 720, margin: "0 auto", textAlign: "right" }}>
      <h3>ایجاد خبر هیئت شهرستان</h3>
      <form onSubmit={handleSubmit}>
        <label>عنوان:
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <label>متن خبر:
          <textarea rows={8} value={content} onChange={(e) => setContent(e.target.value)} />
        </label>

        <label>تصویر شاخص (jpg/png):
          <input
            id="main-image"
            type="file"
            accept="image/*"
            onChange={(e) => setImage(e.target.files?.[0] || null)}
          />
        </label>

        <label>تصاویر الحاقی (چندتایی):
          <input
            id="extra-images"
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => setImages(Array.from(e.target.files))}
          />
        </label>

        {err && <div className="error-msg" style={{ marginTop: 10 }}>{err}</div>}
        {msg && <div className="success-msg" style={{ marginTop: 10 }}>{msg}</div>}

        <button type="submit" className="logout-btn" disabled={submitting} style={{ marginTop: 12 }}>
          {submitting ? "در حال ارسال..." : "ارسال برای تأیید"}
        </button>
      </form>
    </div>
  );
};

export default HeyatCreateNews;
