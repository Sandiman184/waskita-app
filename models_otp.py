# OTP Authentication Models untuk Waskita
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from models import db
import secrets
import string

class RegistrationRequest(db.Model):
    """
    Model untuk menyimpan permintaan registrasi yang menunggu approval admin
    """
    __tablename__ = 'registration_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    full_name = db.Column(db.String(200), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # OTP Fields
    otp_code = db.Column(db.String(6), nullable=False)
    otp_expires_at = db.Column(db.DateTime, nullable=False, index=True)  # Index for performance
    
    # Status Fields
    status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, rejected, expired
    admin_notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)  # Index for cleanup operations
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    approver = relationship('User', foreign_keys=[approved_by])
    
    def __init__(self, username, email, password_hash, full_name=None):
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.full_name = full_name
        self.otp_code = self.generate_otp()
        self.otp_expires_at = datetime.utcnow() + timedelta(minutes=2)
    
    def generate_otp(self):
        """Generate OTP code using configured length"""
        return ''.join(secrets.choice(string.digits) for _ in range(6))
    
    def is_otp_valid(self):
        """Check if OTP is still valid"""
        return datetime.utcnow() < self.otp_expires_at
    
    def regenerate_otp(self):
        """Generate new OTP and extend expiry"""
        self.otp_code = self.generate_otp()
        self.otp_expires_at = datetime.utcnow() + timedelta(minutes=2)
        return self.otp_code

class AdminNotification(db.Model):
    """
    Model untuk notifikasi admin tentang permintaan registrasi
    """
    __tablename__ = 'admin_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    registration_request_id = db.Column(db.Integer, db.ForeignKey('registration_requests.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Notification Fields
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='registration_request')
    
    # Status Fields
    is_read = db.Column(db.Boolean, default=False)
    is_sent = db.Column(db.Boolean, default=False)
    email_sent_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    registration_request = relationship('RegistrationRequest', backref='notifications')
    admin = relationship('User', foreign_keys=[admin_id])
    
    def mark_as_read(self, admin_id):
        """Mark notification as read by admin"""
        self.is_read = True
        self.read_at = datetime.utcnow()
        self.admin_id = admin_id

class OTPEmailLog(db.Model):
    """
    Model untuk logging email OTP yang dikirim
    """
    __tablename__ = 'otp_email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    registration_request_id = db.Column(db.Integer, db.ForeignKey('registration_requests.id'), nullable=False)
    
    # Email Fields
    recipient_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    email_type = db.Column(db.String(50), nullable=False)  # otp_notification, approval_notification
    
    # Status Fields
    is_sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    registration_request = relationship('RegistrationRequest', backref='email_logs')