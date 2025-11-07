-- Waskita Database Schema
-- PostgreSQL Database Schema for Social Media Content Classification System

-- Drop tables if they exist (for clean setup)
DROP TABLE IF EXISTS classification_results CASCADE;
DROP TABLE IF EXISTS clean_data_scraper CASCADE;
DROP TABLE IF EXISTS clean_data_upload CASCADE;
DROP TABLE IF EXISTS raw_data_scraper CASCADE;
DROP TABLE IF EXISTS raw_data CASCADE;
DROP TABLE IF EXISTS datasets CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Create Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    bio TEXT,
    preferences JSON,
    role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    first_login BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    profile_picture VARCHAR(255),
    phone_number VARCHAR(20),
    language_preference VARCHAR(10) DEFAULT 'id',
    timezone VARCHAR(50) DEFAULT 'Asia/Jakarta',
    email_notifications BOOLEAN DEFAULT TRUE,
    theme_preference VARCHAR(20) DEFAULT 'dark'
);

-- Create Datasets table (must be created before raw_data)
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    total_records INTEGER DEFAULT 0,
    cleaned_records INTEGER DEFAULT 0,
    classified_records INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'Mentah',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Raw Data table (for manual uploads)
CREATE TABLE raw_data (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    url TEXT,
    platform VARCHAR(50) NOT NULL,
    source_type VARCHAR(20) DEFAULT 'upload',
    status VARCHAR(20) DEFAULT 'raw',
    file_size BIGINT,
    original_filename VARCHAR(255),
    dataset_id INTEGER REFERENCES datasets(id),
    dataset_name VARCHAR(255),
    uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Raw Data Scraper table (for scraped data)
CREATE TABLE raw_data_scraper (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    url TEXT,
    platform VARCHAR(50) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    scrape_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'raw',
    dataset_id INTEGER REFERENCES datasets(id),
    dataset_name VARCHAR(255),
    scraped_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Clean Data Upload table (cleaned data from manual uploads)
CREATE TABLE clean_data_upload (
    id SERIAL PRIMARY KEY,
    raw_data_id INTEGER NOT NULL REFERENCES raw_data(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    cleaned_content TEXT NOT NULL,
    url TEXT,
    platform VARCHAR(50) NOT NULL,
    dataset_id INTEGER REFERENCES datasets(id),
    cleaned_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Clean Data Scraper table (cleaned data from scraping)
CREATE TABLE clean_data_scraper (
    id SERIAL PRIMARY KEY,
    raw_data_scraper_id INTEGER NOT NULL REFERENCES raw_data_scraper(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    cleaned_content TEXT NOT NULL,
    url TEXT,
    platform VARCHAR(50) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    dataset_id INTEGER REFERENCES datasets(id),
    cleaned_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dataset Statistics Table
CREATE TABLE dataset_statistics (
    id SERIAL PRIMARY KEY,
    total_raw_upload INTEGER DEFAULT 0,
    total_raw_scraper INTEGER DEFAULT 0,
    total_clean_upload INTEGER DEFAULT 0,
    total_clean_scraper INTEGER DEFAULT 0,
    total_classified INTEGER DEFAULT 0,
    total_radikal INTEGER DEFAULT 0,
    total_non_radikal INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Classification Results Table
CREATE TABLE classification_results (
    id SERIAL PRIMARY KEY,
    data_type VARCHAR(20) NOT NULL, -- 'upload' or 'scraper'
    data_id INTEGER NOT NULL, -- ID from clean_data_upload or clean_data_scraper
    model_name VARCHAR(20) NOT NULL, -- model1, model2, model3
    prediction VARCHAR(20) NOT NULL, -- radikal, non-radikal
    probability_radikal FLOAT NOT NULL,
    probability_non_radikal FLOAT NOT NULL,
    classified_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_corrected BOOLEAN DEFAULT FALSE, -- Whether the result has been manually corrected
    corrected_prediction VARCHAR(20), -- Manual correction: radikal, non-radikal
    corrected_by INTEGER REFERENCES users(id), -- Who made the correction
    corrected_at TIMESTAMP -- When the correction was made
);

-- Create indexes for better performance
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_is_active ON users(is_active);
CREATE INDEX idx_users_created_at ON users(created_at);

CREATE INDEX idx_raw_data_uploaded_by ON raw_data(uploaded_by);
CREATE INDEX idx_raw_data_platform ON raw_data(platform);
CREATE INDEX idx_raw_data_status ON raw_data(status);
CREATE INDEX idx_raw_data_created_at ON raw_data(created_at);

CREATE INDEX idx_raw_data_scraper_scraped_by ON raw_data_scraper(scraped_by);
CREATE INDEX idx_raw_data_scraper_platform ON raw_data_scraper(platform);
CREATE INDEX idx_raw_data_scraper_status ON raw_data_scraper(status);
CREATE INDEX idx_raw_data_scraper_created_at ON raw_data_scraper(created_at);

CREATE INDEX idx_clean_data_upload_raw_data_id ON clean_data_upload(raw_data_id);
CREATE INDEX idx_clean_data_upload_cleaned_by ON clean_data_upload(cleaned_by);
CREATE INDEX idx_clean_data_upload_platform ON clean_data_upload(platform);
CREATE INDEX idx_clean_data_upload_dataset_id ON clean_data_upload(dataset_id);
CREATE INDEX idx_clean_data_upload_created_at ON clean_data_upload(created_at);

CREATE INDEX idx_clean_data_scraper_raw_data_scraper_id ON clean_data_scraper(raw_data_scraper_id);
CREATE INDEX idx_clean_data_scraper_cleaned_by ON clean_data_scraper(cleaned_by);
CREATE INDEX idx_clean_data_scraper_platform ON clean_data_scraper(platform);
CREATE INDEX idx_clean_data_scraper_dataset_id ON clean_data_scraper(dataset_id);
CREATE INDEX idx_clean_data_scraper_created_at ON clean_data_scraper(created_at);

CREATE INDEX idx_classification_results_classified_by ON classification_results(classified_by);
CREATE INDEX idx_classification_results_prediction ON classification_results(prediction);
CREATE INDEX idx_classification_results_created_at ON classification_results(created_at);
CREATE INDEX idx_classification_results_data_type ON classification_results(data_type);
CREATE INDEX idx_classification_results_data_id ON classification_results(data_id);
CREATE INDEX idx_classification_results_model_name ON classification_results(model_name);
CREATE INDEX idx_classification_results_data_type_id ON classification_results(data_type, data_id);

-- Create full-text search indexes
CREATE INDEX idx_clean_data_upload_content_fts ON clean_data_upload USING gin(to_tsvector('indonesian', content));
CREATE INDEX idx_clean_data_scraper_content_fts ON clean_data_scraper USING gin(to_tsvector('indonesian', content));

-- Create views for easier data access
CREATE VIEW v_user_statistics AS
SELECT 
    u.id,
    u.username,
    u.email,
    u.role,
    u.created_at,
    u.last_login,
    COUNT(DISTINCT rd.id) as total_uploads,
    COUNT(DISTINCT rds.id) as total_scraping_jobs,
    COUNT(DISTINCT cdu.id) as total_cleaned_upload_data,
    COUNT(DISTINCT cds.id) as total_cleaned_scraper_data,
    COUNT(DISTINCT cr.id) as total_classifications,
    COUNT(DISTINCT CASE WHEN cr.prediction = 'radikal' THEN cr.id END) as radikal_count,
    COUNT(DISTINCT CASE WHEN cr.prediction = 'non-radikal' THEN cr.id END) as non_radikal_count
FROM users u
LEFT JOIN raw_data rd ON u.id = rd.uploaded_by
LEFT JOIN raw_data_scraper rds ON u.id = rds.scraped_by
LEFT JOIN clean_data_upload cdu ON u.id = cdu.cleaned_by
LEFT JOIN clean_data_scraper cds ON u.id = cds.cleaned_by
LEFT JOIN classification_results cr ON u.id = cr.classified_by
GROUP BY u.id, u.username, u.email, u.role, u.created_at, u.last_login;

CREATE VIEW v_classification_summary AS
SELECT 
    DATE(created_at) as classification_date,
    prediction,
    COUNT(*) as count,
    AVG(probability_radikal) as avg_probability_radikal,
    AVG(probability_non_radikal) as avg_probability_non_radikal
FROM classification_results
GROUP BY DATE(created_at), prediction
ORDER BY classification_date DESC;

CREATE VIEW v_platform_statistics AS
SELECT 
    platform,
    COUNT(*) as total_posts
FROM (
    SELECT platform FROM clean_data_upload
    UNION ALL
    SELECT platform FROM clean_data_scraper
) combined_data
GROUP BY platform;

-- Insert default admin user (password: admin123)
INSERT INTO users (username, email, password_hash, role, full_name) VALUES 
('admin', 'admin@waskita.com', 'scrypt:32768:8:1$YourHashHere$YourActualHashValueHere', 'admin', 'Administrator'),
('demo_user', 'user@waskita.com', 'scrypt:32768:8:1$YourHashHere$YourActualHashValueHere', 'user', 'Demo User');

-- Create triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_last_login()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_login = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Note: Trigger will be created in the application code when user logs in

-- Create function to get user activity summary
CREATE OR REPLACE FUNCTION get_user_activity_summary(user_id_param INTEGER)
RETURNS TABLE(
    total_uploads BIGINT,
    total_scraping_jobs BIGINT,
    total_cleaned_data BIGINT,
    total_classifications BIGINT,
    radikal_count BIGINT,
    non_radikal_count BIGINT,
    last_activity TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT rd.id) as total_uploads,
        COUNT(DISTINCT rds.id) as total_scraping_jobs,
        (COUNT(DISTINCT cdu.id) + COUNT(DISTINCT cds.id)) as total_cleaned_data,
        COUNT(DISTINCT cr.id) as total_classifications,
        COUNT(DISTINCT CASE WHEN cr.prediction = 'radikal' THEN cr.id END) as radikal_count,
        COUNT(DISTINCT CASE WHEN cr.prediction = 'non-radikal' THEN cr.id END) as non_radikal_count,
        GREATEST(
            MAX(rd.created_at),
            MAX(rds.created_at),
            MAX(cdu.created_at),
            MAX(cds.created_at),
            MAX(cr.created_at)
        ) as last_activity
    FROM users u
    LEFT JOIN raw_data rd ON u.id = rd.uploaded_by
    LEFT JOIN raw_data_scraper rds ON u.id = rds.scraped_by
    LEFT JOIN clean_data_upload cdu ON u.id = cdu.cleaned_by
    LEFT JOIN clean_data_scraper cds ON u.id = cds.cleaned_by
    LEFT JOIN classification_results cr ON u.id = cr.classified_by
    WHERE u.id = user_id_param
    GROUP BY u.id;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- OTP SYSTEM TABLES (Added for registration and first login OTP functionality)
-- =============================================================================

-- Drop OTP tables if they exist (for clean setup)
DROP TABLE IF EXISTS otp_email_logs CASCADE;
DROP TABLE IF EXISTS admin_notifications CASCADE;
DROP TABLE IF EXISTS registration_requests CASCADE;

-- Create registration_requests table
CREATE TABLE registration_requests (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL,
    full_name VARCHAR(200),
    password_hash VARCHAR(255) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    otp_expires_at TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    approved_at TIMESTAMP,
    approved_by INTEGER REFERENCES users(id)
);

-- Create admin_notifications table
CREATE TABLE admin_notifications (
    id SERIAL PRIMARY KEY,
    registration_request_id INTEGER NOT NULL REFERENCES registration_requests(id),
    admin_id INTEGER REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) DEFAULT 'registration_request' NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    is_sent BOOLEAN DEFAULT FALSE NOT NULL,
    email_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    read_at TIMESTAMP
);

-- Create otp_email_logs table
CREATE TABLE otp_email_logs (
    id SERIAL PRIMARY KEY,
    registration_request_id INTEGER NOT NULL REFERENCES registration_requests(id),
    recipient_email VARCHAR(120) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    email_type VARCHAR(50) NOT NULL,
    is_sent BOOLEAN DEFAULT FALSE NOT NULL,
    sent_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for OTP tables
CREATE INDEX idx_registration_requests_otp_expires_at ON registration_requests(otp_expires_at);
CREATE INDEX idx_registration_requests_status ON registration_requests(status);
CREATE INDEX idx_registration_requests_created_at ON registration_requests(created_at);
CREATE INDEX idx_admin_notifications_registration_request_id ON admin_notifications(registration_request_id);
CREATE INDEX idx_admin_notifications_admin_id ON admin_notifications(admin_id);
CREATE INDEX idx_admin_notifications_is_read ON admin_notifications(is_read);
CREATE INDEX idx_admin_notifications_is_sent ON admin_notifications(is_sent);
CREATE INDEX idx_otp_email_logs_registration_request_id ON otp_email_logs(registration_request_id);
CREATE INDEX idx_otp_email_logs_email_type ON otp_email_logs(email_type);
CREATE INDEX idx_otp_email_logs_is_sent ON otp_email_logs(is_sent);
CREATE INDEX idx_otp_email_logs_created_at ON otp_email_logs(created_at);

-- =============================================================================
-- USER ACTIVITY LOGGING TABLE (digunakan oleh utils.generate_activity_log)
-- =============================================================================

-- Drop if exists for clean setup
DROP TABLE IF EXISTS user_activities CASCADE;

-- Create user_activities table
CREATE TABLE user_activities (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    details TEXT,
    icon VARCHAR(50) DEFAULT 'fa-info-circle',
    color VARCHAR(20) DEFAULT 'blue',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for user_activities
CREATE INDEX idx_user_activities_user_id ON user_activities(user_id);
CREATE INDEX idx_user_activities_created_at ON user_activities(created_at);

-- Additional indexes for datasets
CREATE INDEX idx_datasets_name ON datasets(name);
CREATE INDEX idx_datasets_uploaded_by ON datasets(uploaded_by);

-- Grant permissions (adjust as needed for your setup)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO waskita_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO waskita_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO waskita_user;

COMMIT;