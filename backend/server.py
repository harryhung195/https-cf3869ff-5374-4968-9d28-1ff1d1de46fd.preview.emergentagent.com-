from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
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

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# JWT settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-here')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Security
security = HTTPBearer()

# Models
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

# Auth helpers
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

# Initialize sample products
async def init_sample_products():
    existing_products = await db.products.count_documents({})
    if existing_products == 0:
        sample_products = [
            # Electronics
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
            Product(
                name="Laptop",
                description="High-performance laptop for work and gaming",
                price=1299.99,
                category="Electronics",
                image_url="https://images.unsplash.com/photo-1498049794561-7780e7231661"
            ),
            # T-Shirts
            Product(
                name="Premium Cotton T-Shirt",
                description="Comfortable cotton t-shirt in multiple colors",
                price=29.99,
                category="T-Shirts",
                image_url="https://images.pexels.com/photos/996329/pexels-photo-996329.jpeg"
            ),
            Product(
                name="Designer White Tee",
                description="Stylish white t-shirt with perfect fit",
                price=39.99,
                category="T-Shirts",
                image_url="https://images.unsplash.com/photo-1574180566232-aaad1b5b8450"
            ),
            Product(
                name="Graphic T-Shirt",
                description="Trendy graphic t-shirt for casual wear",
                price=24.99,
                category="T-Shirts",
                image_url="https://images.pexels.com/photos/996329/pexels-photo-996329.jpeg"
            ),
            # Shoes
            Product(
                name="Running Sneakers",
                description="Lightweight running shoes for optimal performance",
                price=129.99,
                category="Shoes",
                image_url="https://images.unsplash.com/photo-1560769629-975ec94e6a86"
            ),
            Product(
                name="Designer Red Sneakers",
                description="Stylish red sneakers for fashion-forward individuals",
                price=159.99,
                category="Shoes",
                image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff"
            ),
            Product(
                name="Casual Shoes",
                description="Comfortable casual shoes for everyday wear",
                price=89.99,
                category="Shoes",
                image_url="https://images.unsplash.com/photo-1560769629-975ec94e6a86"
            ),
        ]
        
        for product in sample_products:
            await db.products.insert_one(product.dict())

# Auth routes
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

# Product routes
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

# Cart routes
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
        # Check if item already exists
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

# Payment routes (placeholder for Stripe integration)
@api_router.post("/payments/checkout")
async def create_checkout_session(checkout_data: CheckoutRequest, current_user: UserResponse = Depends(get_current_user)):
    # Calculate total amount
    total_amount = 0.0
    for item in checkout_data.items:
        product = await db.products.find_one({"id": item.product_id})
        if product:
            total_amount += product["price"] * item.quantity
    
    # For now, return a placeholder response
    # This will be replaced with actual Stripe integration
    return {
        "message": "Checkout session created",
        "total_amount": total_amount,
        "items": checkout_data.items,
        "note": "Stripe integration pending - need secret key"
    }

# Include the router in the main app
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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