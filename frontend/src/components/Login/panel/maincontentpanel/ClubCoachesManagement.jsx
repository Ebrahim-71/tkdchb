import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import Modal from "../../../common/Modal";
import "./ClubCoachesManagement.css";

const ClubCoachesManagement = () => {
  const [allCoaches, setAllCoaches] = useState([]);
  const [selectedCoaches, setSelectedCoaches] = useState([]);
  const [modal, setModal] = useState(null);
  const [confirmChanges, setConfirmChanges] = useState(false);
  const [loading, setLoading] = useState(false);

  const role = localStorage.getItem("user_role");
  const token = localStorage.getItem(`${role}_token`);

  useEffect(() => {
    const fetchCoaches = async () => {
      try {
        const res = await axios.get("https://api.chbtkd.ir/api/auth/club/all-coaches/", {
          headers: { Authorization: `Bearer ${token}` },
        });
        const active = res.data.filter(c => c.is_active).map(c => c.id);
        setAllCoaches(res.data);
        setSelectedCoaches(active);
      } catch (err) {
        console.error("خطا در دریافت لیست مربیان", err);
      }
    };

    fetchCoaches();
  }, []);

  const toggleCoach = (coach) => {
    if (selectedCoaches.includes(coach.id)) {
      setModal({
        type: "remove",
        coach,
      });
    } else {
      if (coach.club_count >= 3) {
        alert(`مربی ${coach.full_name} در ۳ باشگاه ثبت شده است و امکان انتخاب ندارد.`);
        return;
      }
      setSelectedCoaches([...selectedCoaches, coach.id]);
    }
  };

  const handleRemoveConfirmed = () => {
    setSelectedCoaches(selectedCoaches.filter(id => id !== modal.coach.id));
    setModal(null);
  };

  const handleSubmit = () => {
    setConfirmChanges(true);
  };

  const confirmFinalSubmit = async () => {
    try {
      setLoading(true);
      await axios.post("https://api.chbtkd.ir/api/auth/club/update-coaches/", {
        selected_coaches: selectedCoaches,
      }, {
        headers: { Authorization: `Bearer ${token}` },
      });
      alert("درخواست‌ها ارسال شدند.");
    } catch (err) {
      console.error("خطا در ارسال درخواست‌ها", err);
      alert("ارسال درخواست با خطا مواجه شد.");
    } finally {
      setLoading(false);
      setConfirmChanges(false);
    }
  };

  return (
    <div className="coach-management">
      <h2>مدیریت مربیان باشگاه</h2>
      <div className="coach-header">
        <div>نام مربی</div>
        <div>کد ملی</div>
        <div>درجه کمربند</div>
        <div>موبایل </div>
        <div>انتخاب</div>
      </div>

      <PaginatedList
        items={allCoaches}
        itemsPerPage={10}
        renderItem={(coach) => (
          <div className="coach-row">
            <div>
              {coach.full_name}
              {coach.pending_status && (
                <span className="pending-badge">
                  {coach.pending_status === "add" ? " (در انتظار افزودن)" : " (در انتظار حذف)"}
                </span>
              )}
            </div>
            <div>{coach.national_code}</div>
            <div>{coach.belt_grade}</div>
            <div>{coach.phone || "-"}</div>
            <div>
              <input
                type="checkbox"
                checked={selectedCoaches.includes(coach.id)}
                disabled={!!coach.pending_status}
                onChange={() => toggleCoach(coach)}
              />
            </div>
          </div>
        )}
      />

      <div className="submit-wrapper">
        <button className="confirm-btn" onClick={handleSubmit} disabled={loading}>
          {loading ? "در حال ارسال..." : "تأیید"}
        </button>
      </div>

      {modal && (
        <Modal
          title="حذف مربی"
          message={`آیا مطمئن هستید که مربی ${modal.coach.full_name} را می‌خواهید حذف کنید؟`}
          onConfirm={handleRemoveConfirmed}
          onCancel={() => setModal(null)}
        />
      )}

      {confirmChanges && (
        <Modal
          title="تأیید نهایی"
          message="آیا از تغییرات انجام‌شده مطمئن هستید؟"
          onConfirm={confirmFinalSubmit}
          onCancel={() => setConfirmChanges(false)}
        />
      )}
    </div>
  );
};

export default ClubCoachesManagement;
