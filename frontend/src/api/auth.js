import React, { useState } from 'react';
import { Modal, Box, TextField, Button, Typography } from '@mui/material';
import { sendOTP, verifyOTP } from '../../api/auth';
import { useNavigate } from 'react-router-dom';

const AuthModal = ({ open, handleClose, role }) => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState(1);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const handleSendCode = async () => {
    if (!phone || !role) {
      setError('شماره موبایل الزامی است');
      return;
    }
    const result = await sendOTP(phone);
    if (result.success) {
      setStep(2);
    } else {
      setError(result.error || 'خطا در ارسال کد');
    }
  };

  const handleVerify = async () => {
    const result = await verifyOTP(phone, code);
    if (result.success) {
      if (role === 'player') {
        navigate('/register-player', { state: { role: 'player', phone } });
      } else if (role === 'coach') {
        navigate('/register-coach', { state: { phone } });
      } else if (role === 'club') {
        navigate('/register-club', { state: { phone } });
      } else if (role === 'heyat') {
        navigate('/register-heyat', { state: { phone } });
      }
    } else {
      setError(result.error || 'کد تایید اشتباه است');
    }
  };

  return (
    <Modal open={open} onClose={handleClose}>
      <Box sx={{ p: 4, backgroundColor: '#fff', maxWidth: 400, mx: 'auto', mt: 10, borderRadius: 2 }}>
        <Typography variant="h6" gutterBottom>ورود / ثبت‌نام</Typography>

        {step === 1 && (
          <>
            <TextField
              fullWidth
              label="شماره موبایل"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              margin="normal"
            />
            {error && <Typography color="error" mt={1}>{error}</Typography>}
            <Button fullWidth variant="contained" onClick={handleSendCode} sx={{ mt: 2 }}>ارسال کد</Button>
          </>
        )}

        {step === 2 && (
          <>
            <TextField
              fullWidth
              label="کد تایید"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              margin="normal"
            />
            {error && <Typography color="error" mt={1}>{error}</Typography>}
            <Button fullWidth variant="contained" onClick={handleVerify} sx={{ mt: 2 }}>تایید و ادامه</Button>
          </>
        )}
      </Box>
    </Modal>
  );
};

export default AuthModal;