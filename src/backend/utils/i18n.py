from flask import current_app
from flask_login import current_user

TRANSLATIONS = {
    'en': {
        # Status
        'Mentah': 'Raw',
        'Dibersihkan': 'Cleaned',
        'Terklasifikasi': 'Classified',
        'Terkirim': 'Submitted',
        'Selesai': 'Completed',
        'Processing': 'Processing',
        
        # Flash Messages - Auth
        'Ini adalah login pertama Anda. Silakan cek email untuk instruksi lebih lanjut.': 'This is your first login. Please check your email for further instructions.',
        'Gagal mengirim email OTP. Silakan hubungi administrator atau coba lagi nanti.': 'Failed to send OTP email. Please contact administrator or try again later.',
        'Login berhasil!': 'Login successful!',
        'Username atau password salah!': 'Invalid username or password!',
        'Terdapat kesalahan dalam form. Silakan coba lagi.': 'There are errors in the form. Please try again.',
        'Anda telah logout.': 'You have been logged out.',
        'Silakan login untuk mengakses halaman ini.': 'Please login to access this page.',
        
        # Notifications
        'Berhasil meng-upload dataset': 'Dataset uploaded successfully',
        'Gagal meng-upload dataset': 'Failed to upload dataset',
        'Data berhasil dibersihkan': 'Data cleaned successfully',
        
        # UI Elements
        'Uploaded Data': 'Uploaded Data',
        'Scraped Data': 'Scraped Data',
        'Cleaned Data': 'Cleaned Data',
        'Classified': 'Classified',
        
        # Actions
        'melihat': 'view',
        'mengedit': 'edit',
        'menghapus': 'delete',
        'membuat': 'create',
        'mengakses': 'access',
        
        # Permissions
        'Akses diberikan sebagai administrator': 'Access granted as administrator',
        'Akses diberikan': 'Access granted',
        'Akses ditolak!': 'Access denied!',
        
        # Warnings
        'Pilih dataset terlebih dahulu': 'Please select a dataset first',
        'Anda tidak memiliki izin untuk mengakses dataset ini': 'You do not have permission to access this dataset',
        
        # Flash Messages - Dataset
        'Tidak ada file yang dipilih': 'No file selected',
        'File harus memiliki kolom content/text/tweet/komentar': 'File must have content/text/tweet/komentar column',
        'Dataset berhasil diupload': 'Dataset uploaded successfully',
        'Error processing file': 'Error processing file',
        'Format file tidak didukung. Gunakan CSV atau Excel.': 'File format not supported. Use CSV or Excel.',
        
        # Flash Messages - Admin Database
        'File harus berformat .sql': 'File must be in .sql format',
        'Database berhasil direstore dari SQL': 'Database restored from SQL successfully',
        'Gagal melakukan restore SQL': 'Failed to restore SQL',
        'Logs berhasil direset': 'Logs reset successfully',
        'Gagal mereset logs': 'Failed to reset logs',
        'Database berhasil direset (User data tetap aman)': 'Database reset successfully (User data remains safe)',
        'Gagal mereset database': 'Failed to reset database',
        'Scraping': 'Scraping',
        'Upload': 'Upload',
        'Raw': 'Raw',
    }
}

def t(text):
    """
    Translate text based on current user's language preference.
    Defaults to Indonesian (original text) if language is 'id' or translation not found.
    """
    try:
        # Check if user is authenticated and has preferences
        lang = 'id'
        if current_user and current_user.is_authenticated:
            prefs = current_user.get_preferences()
            lang = prefs.get('language', 'id')
        
        # If language is Indonesian, return original text
        if lang == 'id':
            return text
            
        # If language is English, look up translation
        if lang == 'en':
            return TRANSLATIONS['en'].get(text, text)
            
        return text
    except Exception:
        # Fallback to original text on any error
        return text
