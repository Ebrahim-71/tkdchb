// ✅ فایل: PlayerRegisterModal.jsx
import React, { useState, useEffect, useRef } from 'react';
import './RegisterModal.css';
import { useNavigate } from 'react-router-dom';

const PlayerRegisterModal = ({ onClose, role }) => {
  const [step, setStep] = useState(1);
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState(['', '', '', '']);
  const [timer, setTimer] = useState(0);
  const inputRefs = useRef([]);
  const [error, setError] = useState('');
  const [cooldownActive, setCooldownActive] = useState(false);
  const navigate = useNavigate();

  
  // شمارش معکوس
  useEffect(() => {
    if (cooldownActive && timer > 0) {
      const countdown = setInterval(() => setTimer(prev => prev - 1), 1000);
      return () => clearInterval(countdown);
    }
    if (timer === 0 && cooldownActive) {
      setCooldownActive(false);
    }
  }, [cooldownActive, timer]);

  // اتوفوکوس و انتقال بین inputها از چپ به راست
  const handleCodeChange = (value, index) => {
    if (!/^\d?$/.test(value)) return;
    const newCode = [...code];
    newCode[index] = value;
    setCode(newCode);

    if (value && index < 3) inputRefs.current[index + 1].focus();
    if (newCode.every(d => d.length === 1)) verifyCode(newCode.join(''));
  };

  const sendPhone = () => {
    if (!/^09\d{9}$/.test(phone)) return setError('شماره معتبر نیست');
    if (cooldownActive) return setError('لطفاً تا پایان شمارنده صبر کنید');

    setError('');
    fetch('https://api.chbtkd.ir/api/auth/send-code/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ phone, role })  // ✅ نقش اضافه شد
})

      .then(async res => {
  const data = await res.json();
  if (!res.ok) {
    if (data.retry_after) {
      setStep(2);
      setTimer(data.retry_after);
      setCooldownActive(true);
    }

    // اگر پیام خاصی در پاسخ هست، اون رو نمایش بده
    if (data.phone) return setError(data.phone);
    if (data.error) return setError(data.error);

    return setError('خطا در ارسال کد');
  }

  setStep(2);
  setTimer(180);
  setCooldownActive(true);
})

      .catch(() => setError('خطا در ارتباط با سرور'));
  };
  const getTitleFromRole = (role) => {
  switch (role) {
    case 'player':
      return 'بازیکن';
    case 'coach':
      return 'مربی | داور';
    case 'club':
      return 'باشگاه';
    case 'heyat':
      return 'هیئت';
    default:
      return 'کاربر';
  }
};

  const resendCode = () => {
    if (cooldownActive) return setError('لطفاً صبر کنید');
    sendPhone(); // دوباره همان تابع را صدا بزن
  };

  const verifyCode = (codeStr) => {
  fetch('https://api.chbtkd.ir/api/auth/verify-code/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, code: codeStr })
  })
    .then(res => res.json())
    .then(data => {
      if (data.message) {
        localStorage.setItem("verifiedPhone", phone);  // اگر خواستی بعداً ازش استفاده کنی
        navigate(`/register-${role || 'player'}`, { state: { role } });


      
      } else {
        setError('کد اشتباه است');
        setCode(['', '', '', '']);
        inputRefs.current[0].focus();
      }
    });
};


  return (
    <div className="modal-backdrop">
      <div className="modal-container animate-pop">
        <button className="close-btn" onClick={onClose}>&times;</button>
        {step === 1 && (
          <div className="modal-content">
            <h2>ثبت‌نام {getTitleFromRole(role)}</h2>

            <p className="subtext">لطفاً شماره موبایل خود را وارد نمایید</p>
            <input
              className="input-field"
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="مثلاً 09123456789"
              dir="rtl"
            />
            {error && <p className="error-msg">{error}</p>}
            <button className="action-btn" onClick={sendPhone} disabled={cooldownActive}>
              {cooldownActive ? `صبر کنید (${timer})` : 'ارسال کد'}
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="modal-content">
            <h2>کد تایید</h2>
            <p className="subtext">کد پیامک شده را وارد کنید</p>
            <div className="code-inputs" dir="ltr">
              {code.map((val, i) => (
                <input
                  key={i}
                  type="text"
                  maxLength="1"
                  ref={el => inputRefs.current[i] = el}
                  value={val}
                  onChange={e => handleCodeChange(e.target.value, i)}
                  className="code-box"
                  autoComplete="one-time-code"
                />
              ))}
            </div>
            {error && <p className="error-msg">{error}</p>}
            {timer > 0 ? (
              <p className="timer">ارسال مجدد تا <strong>{timer}</strong> ثانیه</p>
            ) : (
              <button className="resend-btn" onClick={resendCode}>
                &#x21bb; ارسال مجدد کد
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default PlayerRegisterModal;
