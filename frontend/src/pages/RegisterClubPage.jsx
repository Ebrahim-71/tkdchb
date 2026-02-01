import React, { useState } from 'react';
import StepOneClub from '../components/Register/stepsclub/StepOneClub';
import StepTwoClub from '../components/Register/stepsclub/StepTwoClub';
import StepThreeClub from '../components/Register/stepsclub/StepThreeClub';
import sampleImg from '../assets/img/register-cover.jpg';
import '../components/Register/stepsclub/ClubRegister.css';

const SuccessModal = ({ message, onClose }) => (
  <div className="modal-error-overlay">
    <div className="modal-error-box">
      <p>{message}</p>
      <button onClick={onClose}>باشه</button>
    </div>
  </div>
);

const ErrorModal = ({ errors, onClose }) => (
  <div className="modal-error-overlay">
    <div className="modal-error-box">
      {errors.map((err, i) => (
        <p key={i}>{err}</p>
      ))}
      <button onClick={onClose}>باشه</button>
    </div>
  </div>
);

const RegisterClubPage = () => {
  const [step, setStep] = useState(1);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [customErrors, setCustomErrors] = useState([]);
  const [showErrorModal, setShowErrorModal] = useState(false);

  const verifiedPhone = localStorage.getItem('verifiedPhone') || '';

  const [formData, setFormData] = useState({
    club_name: '',
    founder_name: '',
    founder_national_code: '',
    founder_phone: verifiedPhone,
    club_type: '',
    activity_description: '',
    province: '',
    county: '',
    city: '',
    tkd_board: '',
    phone: '',
    address: '',
    license_number: '',
    federation_id: '',
    license_image: null,
    confirm_info: false,
  });

  const handleDataChange = (newData) => {
    setFormData((prev) => ({ ...prev, ...newData }));
  };

  const getCookie = (name) => {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  };

  const handleSubmit = () => {
    const form = new FormData();
    Object.entries(formData).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        form.append(key, value);
      }
    });

    const csrfToken = getCookie('csrftoken');

    fetch('https://api.chbtkd.ir/api/auth/register-club/', {
      method: 'POST',
      body: form,
      headers: {
        'X-CSRFToken': csrfToken,
      },
      credentials: 'include',
    })
      .then(async (res) => {
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
          setSuccessMessage(data.message || 'باشگاه با موفقیت ثبت شد و در انتظار تایید هیئت استان میباشد.');
          setShowSuccessModal(true);
          localStorage.removeItem('verifiedPhone');
        } else {
          const errors = data.errors || {};
          const messages = Object.entries(errors).map(
            ([key, val]) => `${key}: ${Array.isArray(val) ? val.join(', ') : val}`
          );
          setCustomErrors(messages);
          setShowErrorModal(true);
        }
      })
      .catch((err) => {
        console.error('Error:', err);
        setCustomErrors(['خطای ارتباط با سرور. لطفاً اتصال خود را بررسی کنید.']);
        setShowErrorModal(true);
      });
  };

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <StepOneClub
            data={formData}
            onDataChange={handleDataChange}
            onNext={() => setStep(2)}
          />
        );
      case 2:
        return (
          <StepTwoClub
            data={formData}
            onDataChange={handleDataChange}
            onNext={() => setStep(3)}
            onBack={() => setStep(1)}
          />
        );
      case 3:
        return (
          <StepThreeClub
            data={formData}
            onDataChange={handleDataChange}
            onSubmit={handleSubmit}
            onBack={() => setStep(2)}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="register-page">
      <div className="register-form-section">{renderStep()}</div>
      <div className="register-image-section">
        <img src={sampleImg} alt="register visual" />
      </div>

      {showSuccessModal && (
        <SuccessModal
          message={successMessage}
          onClose={() => {
            setShowSuccessModal(false);
            window.location.href = '/';
          }}
        />
      )}

      {showErrorModal && (
        <ErrorModal
          errors={customErrors}
          onClose={() => setShowErrorModal(false)}
        />
      )}
    </div>
  );
};

export default RegisterClubPage;
