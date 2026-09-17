from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
import bcrypt
from sqlalchemy.orm import Session
from src.database import User, get_db

# 密钥，实际应用中应从环境变量获取
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/token",
    auto_error=False  # 不自动抛出错误，让我们可以自定义处理
)

def verify_password(plain_password, hashed_password):
    try:
        # 在一些情况下，密码可能不是使用bcrypt哈希的
        # 或者哈希格式不正确，这里添加错误处理
        # print(f"尝试验证密码：{plain_password}")
        # print(f"使用哈希：{hashed_password}")
        
        # 检查是否是bcrypt哈希
        hashed_password = hashed_password.strip()
        if not hashed_password.startswith('$2'):
            # print("警告：存储的密码不是bcrypt哈希格式，将直接比较明文")
            return plain_password == hashed_password
        
        # 解决bcrypt类型转换问题
        try:
            # 确保密码是字节类型
            if isinstance(plain_password, str):
                plain_password = plain_password.encode('utf-8')
            
            if isinstance(hashed_password, str):
                hashed_password = hashed_password.encode('utf-8')
                
            # 使用bcrypt直接验证
            result = bcrypt.checkpw(plain_password, hashed_password)
            # print(f"密码验证结果：{result}")
            return result
        except Exception as e:
            # print(f"bcrypt直接验证失败: {str(e)}")
            # 如果bcrypt直接验证失败，使用pwd_context作为备选方案
            return pwd_context.verify(str(plain_password), str(hashed_password))
            
    except Exception as e:
        # print(f"密码验证出错: {str(e)}")
        # 验证出错时，尝试直接比较（紧急回退策略）
        return plain_password == hashed_password

def get_password_hash(password):
    return pwd_context.hash(password).strip()

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    
    # 打印一些调试信息
    # print(f"Authenticating user: {username}")
    # print(f"Password provided: {password}")
    # print(f"Stored password hash: {user.password_hash}")
    
    if not verify_password(password, user.password_hash):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

def check_admin_permission(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return user