# server/app.py
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import os
import re
import uuid
from datetime import datetime, timezone
import logging
from functools import wraps


# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)


allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'https://client-two-swart.vercel.app').split(',')
CORS(app, origins=allowed_origins,supports_credentials=True)
# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Models
class DeliveryBoy(db.Model):
    __tablename__ = 'delivery_boys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    status = db.Column(db.Enum('free', 'occupied'), default='free')
    current_order_id = db.Column(db.String(50), nullable=True)
    deliveries_today = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'status': self.status,
            'current_order_id': self.current_order_id,
            'deliveries_today': self.deliveries_today,
            'is_active': self.is_active
        }

class CallLog(db.Model):
    __tablename__ = 'call_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    delivery_boy_id = db.Column(db.Integer, db.ForeignKey('delivery_boys.id'), nullable=False)
    client_number = db.Column(db.String(20), nullable=False)
    order_id = db.Column(db.String(50), nullable=False)
    call_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    call_status = db.Column(db.Enum('connected', 'busy', 'no_answer', 'failed'), default='connected')
    call_duration = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    
    delivery_boy = db.relationship('DeliveryBoy', backref='call_logs')
    
    def to_dict(self):
        return {
            'id': self.id,
            'delivery_boy_id': self.delivery_boy_id,
            'delivery_boy_name': self.delivery_boy.name,
            'client_number': self.client_number,
            'order_id': self.order_id,
            'call_time': self.call_time.isoformat(),
            'call_status': self.call_status,
            'call_duration': self.call_duration
        }

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'delivery_boy_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Utility functions
def validate_phone(phone):
    """Validate Indian phone number format"""
    pattern = r'^\+91[6-9]\d{9}$'
    return re.match(pattern, phone) is not None

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_order_id():
    """Generate unique order ID"""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    random_suffix = str(uuid.uuid4())[:4].upper()
    return f"ORD{timestamp}{random_suffix}"

# API Routes
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        # Validation
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        if not phone or not validate_phone(phone):
            return jsonify({'error': 'Invalid phone number format. Use +91XXXXXXXXXX'}), 400
        
        if not password or len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        if email and not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Check if delivery boy already exists
        existing_delivery_boy = DeliveryBoy.query.filter(
            (DeliveryBoy.phone == phone) | 
            (DeliveryBoy.email == email if email else False)
        ).first()
        
        if existing_delivery_boy:
            if existing_delivery_boy.phone == phone:
                return jsonify({'error': 'Phone number already registered'}), 400
            else:
                return jsonify({'error': 'Email already registered'}), 400
        
        # Create new delivery boy
        delivery_boy = DeliveryBoy(
            name=name,
            phone=phone,
            email=email if email else None
        )
        delivery_boy.set_password(password)
        
        db.session.add(delivery_boy)
        db.session.commit()
        
        logger.info(f"New delivery boy registered: {name} ({phone})")
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'delivery_boy': delivery_boy.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error during registration: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        password = data.get('password', '').strip()
        
        if not phone or not password:
            return jsonify({'error': 'Phone number and password are required'}), 400
        
        # Find delivery boy by phone
        delivery_boy = DeliveryBoy.query.filter_by(phone=phone, is_active=True).first()
        
        if not delivery_boy or not delivery_boy.check_password(password):
            return jsonify({'error': 'Invalid phone number or password'}), 401
        
        # Create session
        session['delivery_boy_id'] = delivery_boy.id
        session['delivery_boy_name'] = delivery_boy.name
        
        logger.info(f"Delivery boy logged in: {delivery_boy.name} ({phone})")
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'delivery_boy': delivery_boy.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        return jsonify({'error': 'Login failed. Please try again.'}), 500

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    try:
        delivery_boy_name = session.get('delivery_boy_name', 'Unknown')
        session.clear()
        
        logger.info(f"Delivery boy logged out: {delivery_boy_name}")
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        })
        
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        return jsonify({'error': 'Logout failed'}), 500

@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard():
    try:
        delivery_boy_id = session['delivery_boy_id']
        
        delivery_boy = DeliveryBoy.query.get(delivery_boy_id)
        if not delivery_boy or not delivery_boy.is_active:
            session.clear()
            return jsonify({'error': 'Delivery boy not found or inactive'}), 404
        
        # Get recent call logs
        recent_calls = CallLog.query.filter_by(delivery_boy_id=delivery_boy_id)\
                                  .order_by(CallLog.call_time.desc())\
                                  .limit(5).all()
        
        # Get today's delivery count
        today = datetime.now(timezone.utc).date()
        today_deliveries = CallLog.query.filter(
            CallLog.delivery_boy_id == delivery_boy_id,
            CallLog.call_time >= today
        ).count()
        
        delivery_boy.deliveries_today = today_deliveries
        db.session.commit()
        
        return jsonify({
            'success': True,
            'delivery_boy': delivery_boy.to_dict(),
            'recent_calls': [call.to_dict() for call in recent_calls]
        })
        
    except Exception as e:
        logger.error(f"Error fetching dashboard: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500

@app.route('/api/update-status', methods=['POST'])
@login_required
def update_status():
    try:
        delivery_boy_id = session['delivery_boy_id']
        data = request.get_json()
        
        new_status = data.get('status')
        if new_status not in ['free', 'occupied']:
            return jsonify({'error': 'Invalid status. Use "free" or "occupied"'}), 400
        
        delivery_boy = DeliveryBoy.query.get(delivery_boy_id)
        if not delivery_boy:
            return jsonify({'error': 'Delivery boy not found'}), 404
        
        delivery_boy.status = new_status
        
        # If setting to free, clear current order
        if new_status == 'free':
            delivery_boy.current_order_id = None
        
        db.session.commit()
        
        logger.info(f"Delivery boy {delivery_boy.name} status updated to {new_status}")
        
        return jsonify({
            'success': True,
            'message': f'Status updated to {new_status}',
            'delivery_boy': delivery_boy.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        return jsonify({'error': 'Failed to update status'}), 500

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    try:
        delivery_boy_id = session['delivery_boy_id']
        delivery_boy = DeliveryBoy.query.get(delivery_boy_id)
        
        if not delivery_boy:
            return jsonify({'error': 'Delivery boy not found'}), 404
        
        return jsonify({
            'success': True,
            'delivery_boy': delivery_boy.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        return jsonify({'error': 'Failed to fetch profile'}), 500

@app.route('/api/update-profile', methods=['PUT'])
@login_required
def update_profile():
    try:
        delivery_boy_id = session['delivery_boy_id']
        data = request.get_json()
        
        delivery_boy = DeliveryBoy.query.get(delivery_boy_id)
        if not delivery_boy:
            return jsonify({'error': 'Delivery boy not found'}), 404
        
        # Update allowed fields
        if 'name' in data:
            name = data['name'].strip()
            if name:
                delivery_boy.name = name
        
        if 'email' in data:
            email = data['email'].strip()
            if email and not validate_email(email):
                return jsonify({'error': 'Invalid email format'}), 400
            
            # Check if email is already taken by another user
            if email:
                existing = DeliveryBoy.query.filter(
                    DeliveryBoy.email == email,
                    DeliveryBoy.id != delivery_boy_id
                ).first()
                if existing:
                    return jsonify({'error': 'Email already taken'}), 400
            
            delivery_boy.email = email if email else None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'delivery_boy': delivery_boy.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        return jsonify({'error': 'Failed to update profile'}), 500

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        delivery_boy_id = session['delivery_boy_id']
        data = request.get_json()
        
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password are required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters long'}), 400
        
        delivery_boy = DeliveryBoy.query.get(delivery_boy_id)
        if not delivery_boy:
            return jsonify({'error': 'Delivery boy not found'}), 404
        
        if not delivery_boy.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        delivery_boy.set_password(new_password)
        db.session.commit()
        
        logger.info(f"Password changed for delivery boy: {delivery_boy.name}")
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        return jsonify({'error': 'Failed to change password'}), 500

@app.route('/api/allocate-delivery', methods=['POST'])
def allocate_delivery():
    """Twilio webhook endpoint for incoming calls"""
    try:
        # Get caller's number from Twilio webhook
        caller_number = request.form.get('From')
        
        if not caller_number:
            return jsonify({'error': 'Caller number not provided'}), 400
        
        # Find available delivery boy
        available_delivery_boy = DeliveryBoy.query.filter_by(
            status='free', 
            is_active=True
        ).first()
        
        if not available_delivery_boy:
            # No delivery boys available - play message
            response = VoiceResponse()
            response.say("Sorry, all delivery boys are currently busy. Please try again later.")
            return str(response), 200, {'Content-Type': 'application/xml'}
        
        # Generate order ID and update delivery boy status
        order_id = generate_order_id()
        available_delivery_boy.status = 'occupied'
        available_delivery_boy.current_order_id = order_id
        
        # Create call log
        call_log = CallLog(
            delivery_boy_id=available_delivery_boy.id,
            client_number=caller_number,
            order_id=order_id
        )
        
        db.session.add(call_log)
        db.session.commit()
        
        # Create TwiML response to forward call
        response = VoiceResponse()
        response.say(f"Connecting you to delivery boy {available_delivery_boy.name}")
        
        if twilio_client and TWILIO_PHONE_NUMBER:
            response.dial(available_delivery_boy.phone, caller_id=TWILIO_PHONE_NUMBER)
        else:
            response.say("Call forwarding is not configured. Please contact support.")
        
        logger.info(f"Call from {caller_number} allocated to {available_delivery_boy.name} (Order: {order_id})")
        
        return str(response), 200, {'Content-Type': 'application/xml'}
        
    except Exception as e:
        logger.error(f"Error allocating delivery: {str(e)}")
        
        # Return error message to caller
        response = VoiceResponse()
        response.say("Sorry, there was an error processing your call. Please try again later.")
        return str(response), 200, {'Content-Type': 'application/xml'}

@app.route('/api/call-logs', methods=['GET'])
@login_required
def get_call_logs():
    """Get call logs for the authenticated delivery boy"""
    try:
        delivery_boy_id = session['delivery_boy_id']
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        call_logs = CallLog.query.filter_by(delivery_boy_id=delivery_boy_id)\
                                .order_by(CallLog.call_time.desc())\
                                .paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'success': True,
            'call_logs': [log.to_dict() for log in call_logs.items],
            'total': call_logs.total,
            'pages': call_logs.pages,
            'current_page': page
        })
        
    except Exception as e:
        logger.error(f"Error fetching call logs: {str(e)}")
        return jsonify({'error': 'Failed to fetch call logs'}), 500

@app.route('/api/check-session', methods=['GET'])
def check_session():
    """Check if user is logged in"""
    if 'delivery_boy_id' in session:
        delivery_boy = DeliveryBoy.query.get(session['delivery_boy_id'])
        if delivery_boy and delivery_boy.is_active:
            return jsonify({
                'authenticated': True,
                'delivery_boy': delivery_boy.to_dict()
            })
    
    return jsonify({'authenticated': False})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0'
    })
@app.route('/')
def home():
    return "Welcome to the Delivery API Server!"
# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Initialize database
with app.app_context():
    def create_tables():
        try:
            print("Trying to create tables...")
            db.create_all()
            print("Tables created.")
            logger.info("Database tables created successfully")
        except Exception as e:
            print("Error while creating tables:", str(e))
            logger.error(f"Error creating database tables: {str(e)}")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)