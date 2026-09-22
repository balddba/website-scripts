-- Seed tables and indexes for MySQL script integration testing

USE testdb;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_status (status),
    INDEX idx_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    order_total DECIMAL(10, 2) NOT NULL,
    order_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id),
    INDEX idx_orders_status (order_status),
    INDEX idx_orders_created_at (created_at)
) ENGINE=InnoDB;

-- Insert sample rows
INSERT INTO users (username, email, status) VALUES
    ('jdoe', 'jdoe@example.com', 'active'),
    ('asmith', 'asmith@example.com', 'active'),
    ('bwayne', 'bwayne@example.com', 'inactive')
ON DUPLICATE KEY UPDATE email=VALUES(email);

INSERT INTO orders (user_id, order_total, order_status) VALUES
    (1, 99.95, 'completed'),
    (1, 149.50, 'completed'),
    (2, 29.00, 'pending')
ON DUPLICATE KEY UPDATE order_total=VALUES(order_total);
