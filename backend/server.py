from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import os
import logging
import jwt
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import uuid
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
)

# Load environment variables from .env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Stripe setup
stripe_api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe_checkout = StripeCheckout(api_key=stripe_api_key)

# Create the main app
app = FastAPI()

# Create API router with prefix /api
api_router = APIRouter(prefix="/api")

# JWT settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-here')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Security scheme
security = HTTPBearer()

# Define Pydantic models

class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    email: str
    name: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int = 100
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CartItem(BaseModel):
    product_id: str
    quantity: int

class Cart(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    items: List[CartItem] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PaymentTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: str
    amount: float
    currency: str = "usd"
    status: str = "pending"
    payment_status: str = "unpaid"
    metadata: Dict[str, str] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class CheckoutRequest(BaseModel):
    items: List[CartItem]
    origin_url: str

class PaymentStatusResponse(BaseModel):
    status: str
    payment_status: str
    amount_total: float
    currency: str
    transaction_id: str
    message: str

# Auth helper functions

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = await db.users.find_one({"id": user_id})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return UserResponse(**user)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Initialize sample products on startup if none exist

async def init_sample_products():
    existing_products = await db.products.count_documents({})
    if existing_products == 0:
        sample_products = [
            Product(
                name="Wireless Headphones",
                description="Premium wireless headphones with noise cancellation",
                price=199.99,
                category="Electronics",
                image_url="https://images.unsplash.com/photo-1498049794561-7780e7231661"
            ),
            Product(
                name="Smartphone",
                description="Latest smartphone with advanced camera features",
                price=799.99,
                category="Electronics",
                image_url="https://images.pexels.com/photos/356056/pexels-photo-356056.jpeg"
            ),
            # ... add other products here ...
        ]
        for product in sample_products:
            await db.products.insert_one(product.dict())

# Routes

@api_router.post("/auth/register", response_model=dict)
async def register(user_data: UserCreate):
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = hash_password(user_data.password)
    user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hashed_password
    )
    await db.users.insert_one(user.dict())
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": UserResponse(**user.dict())}

@api_router.post("/auth/login", response_model=dict)
async def login(user_data: UserLogin):
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user["id"]})
    return {"access_token": access_token, "token_type": "bearer", "user": UserResponse(**user)}

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):
    return current_user

@api_router.get("/products", response_model=List[Product])
async def get_products(category: Optional[str] = None, search: Optional[str] = None):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    products = await db.products.find(query).to_list(100)
    return [Product(**product) for product in products]

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**product)

@api_router.get("/categories")
async def get_categories():
    categories = await db.products.distinct("category")
    return {"categories": categories}

@api_router.get("/cart", response_model=Cart)
async def get_cart(current_user: UserResponse = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": current_user.id})
    if not cart:
        cart = Cart(user_id=current_user.id)
        await db.carts.insert_one(cart.dict())
        return cart
    return Cart(**cart)

@api_router.post("/cart/add")
async def add_to_cart(item: CartItem, current_user: UserResponse = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": current_user.id})
    if not cart:
        cart = Cart(user_id=current_user.id, items=[item])
        await db.carts.insert_one(cart.dict())
    else:
        cart_obj = Cart(**cart)
        existing_item = next((i for i in cart_obj.items if i.product_id == item.product_id), None)
        if existing_item:
            existing_item.quantity += item.quantity
        else:
            cart_obj.items.append(item)
        cart_obj.updated_at = datetime.utcnow()
        await db.carts.replace_one({"user_id": current_user.id}, cart_obj.dict())
    return {"message": "Item added to cart"}

@api_router.delete("/cart/remove/{product_id}")
async def remove_from_cart(product_id: str, current_user: UserResponse = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": current_user.id})
    if cart:
        cart_obj = Cart(**cart)
        cart_obj.items = [item for item in cart_obj.items if item.product_id != product_id]
        cart_obj.updated_at = datetime.utcnow()
        await db.carts.replace_one({"user_id": current_user.id}, cart_obj.dict())
    return {"message": "Item removed from cart"}

@api_router.put("/cart/clear")
async def clear_cart(current_user: UserResponse = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": current_user.id})
    if cart:
        cart_obj = Cart(**cart)
        cart_obj.items = []
        cart_obj.updated_at = datetime.utcnow()
        await db.carts.replace_one({"user_id": current_user.id}, cart_obj.dict())
    return {"message": "Cart cleared"}

@api_router.post("/payments/checkout")
async def create_checkout_session(checkout_data: CheckoutRequest, current_user: UserResponse = Depends(get_current_user)):
    total_amount = 0.0
    product_details = []
    for item in checkout_data.items:
        product = await db.products.find_one({"id": item.product_id})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        item_total = float(product["price"]) * item.quantity
        total_amount += item_total
        product_details.append({
            "product_id": item.product_id,
            "name": product["name"],
            "price": product["price"],
            "quantity": item.quantity,
            "total": item_total
        })
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid cart total")
    success_url = f"{checkout_data.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{checkout_data.origin_url}/payment/cancel"
    metadata = {
        "user_id": current_user.id,
        "user_email": current_user.email,
        "product_count": str(len(checkout_data.items)),
        "source": "ecommerce_cart"
    }
    try:
        checkout_request = CheckoutSessionRequest(
            amount=total_amount,
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata
        )
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        payment_transaction = PaymentTransaction(
            user_id=current_user.id,
            session_id=session.session_id,
            amount=total_amount,
            currency="usd",
            status="pending",
            payment_status="unpaid",
            metadata={**metadata, "product_details": str(product_details)}
        )
        await db.payment_transactions.insert_one(payment_transaction.dict())
        return {
            "url": session.url,
            "session_id": session.session_id,
            "amount": total_amount,
            "currency": "usd"
        }
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

@api_router.get("/payments/status/{session_id}", response_model=PaymentStatusResponse)
async def get_payment_status(session_id: str, current_user: UserResponse = Depends(get_current_user)):
    try:
        checkout_status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        transaction = await db.payment_transactions.find_one({"session_id": session_id})
        if not transaction:
            raise HTTPException(status_code=404, detail="Payment transaction not found")
        if transaction["user_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if (transaction["status"] != checkout_status.status or transaction["payment_status"] != checkout_status.payment_status):
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": checkout_status.status,
                        "payment_status": checkout_status.payment_status,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            if checkout_status.payment_status == "paid":
                await db.carts.update_one(
                    {"user_id": current_user.id},
                    {"$set": {"items": [], "updated_at": datetime.utcnow()}}
                )
        return PaymentStatusResponse(
            status=checkout_status.status,
            payment_status=checkout_status.payment_status,
            amount_total=checkout_status.amount_total / 100,  # cents to dollars
            currency=checkout_status.currency,
            transaction_id=transaction["id"],
            message=f"Payment is {checkout_status.payment_status}"
        )
    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get payment status")

@api_router.get("/payments/transactions")
async def get_user_transactions(current_user: UserResponse = Depends(get_current_user)):
    transactions = await db.payment_transactions.find(
        {"user_id": current_user.id}
    ).sort("created_at", -1).to_list(50)
    return [PaymentTransaction(**transaction) for transaction in transactions]

# Include the router in the app
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
allow_origins=["https://https-cf3869ff-5374-4968-9d28-1ff1d-gold.vercel.app"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize sample products on startup
@app.on_event("startup")
async def startup_event():
    await init_sample_products()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
