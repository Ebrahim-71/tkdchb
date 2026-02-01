import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast, ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import "./CoachRequests.css"; // فایل استایل جداگانه برای دکمه‌ها و جدول

const CoachRequests = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [respondingId, setRespondingId] = useState(null);
    const [hasNewRequests, setHasNewRequests] = useState(false);
  const role = localStorage.getItem("user_role");
  const token = localStorage.getItem(`${role}_token`);

  useEffect(() => {
    if (!token) {
      toast.error("توکن یافت نشد. لطفاً دوباره وارد شوید.");
      return;
    }

    const fetchRequests = async () => {
      try {
        const res = await axios.get("https://api.chbtkd.ir/api/auth/coach/requests/", {
          headers: { Authorization: `Bearer ${token}` },
        });
        setRequests(res.data);
         const hasPending = res.data.some((req) => req.status === "pending");
      setHasNewRequests(hasPending);

      } catch (err) {
        console.error("خطا در دریافت درخواست‌ها", err);
        toast.error("خطا در دریافت داده‌ها");
      } finally {
        setLoading(false);
      }
    };

    fetchRequests();
  }, [token]);

  const respond = async (id, action) => {
    setRespondingId(id);
    try {
      await axios.post(
       `https://api.chbtkd.ir/api/auth/coach/requests/${id}/respond/`,
        { action },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      setRequests(prev =>
        prev.map(req =>
          req.id === id ? { ...req, status: action === "accept" ? "accepted" : "rejected" } : req
        )
      );
      toast.success(`درخواست با موفقیت ${action === "accept" ? "تأیید" : "رد"} شد.`);
    } catch (err) {
      console.error("خطا در ارسال پاسخ", err);
      toast.error("پاسخ ثبت نشد.");
    } finally {
      setRespondingId(null);
    }
  };

  if (loading) return <p>در حال دریافت...</p>;

  return (
    <div className="students-table">
      <ToastContainer />
      <h2 className="title">درخواست‌های باشگاه‌ها</h2>
      {requests.length === 0 ? (
        <p style={{ textAlign: "center" }}>درخواستی وجود ندارد.</p>
      ) : (
        <div className="table-container">
          <div className="table-header">
            <div>باشگاه</div>
            <div>نوع درخواست</div>
            <div>وضعیت</div>
            <div>اقدام</div>
          </div>
          {requests.map((req, idx) => (
            <div
              className={`table-row ${idx % 2 === 0 ? "row-light" : "row-dark"}`}
              key={req.id}
            >
              <div>{req.club_name}</div>
              <div>{req.request_type === "add" ? "افزودن" : "حذف"}</div>
              <div>
                {req.status === "pending"
                  ? "در انتظار"
                  : req.status === "accepted"
                  ? "تأیید شده"
                  : "رد شده"}
              </div>
              <div>
                {req.status === "pending" && (
                  <>
                    <button
                      className="btn-accept"
                      onClick={() => respond(req.id, "accept")}
                      disabled={respondingId === req.id}
                    >
                      تأیید
                    </button>{" "}
                    <button
                      className="btn-reject"
                      onClick={() => respond(req.id, "reject")}
                      disabled={respondingId === req.id}
                    >
                      رد
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default CoachRequests;
