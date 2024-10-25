from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Union, Optional
import pandas as pd
import logging
from fastapi.responses import StreamingResponse
import io
import csv
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, select
from contextlib import asynccontextmanager

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_URL = "postgresql+asyncpg://chris:AMDilike@localhost:5432/test"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 创建基类
Base = declarative_base()

# 定义模型
class SizeRecord(Base):
    __tablename__ = 'size_records'

    id = Column(Integer, primary_key=True)
    序号 = Column(Integer)
    姓名 = Column(String)
    尺码 = Column(String)
    创建时间 = Column(DateTime, default=datetime.utcnow)

# 异步上下文管理器用于数据库会话
@asynccontextmanager
async def get_session():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库操作错误: {str(e)}")
            raise

# 应用生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # 启动时执行
        logger.info("正在初始化数据库...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库初始化完成")
        
        yield
        
    except Exception as e:
        logger.error(f"应用启动错误: {str(e)}")
        raise
    finally:
        # 关闭时执行
        logger.info("正在关闭应用...")
        await engine.dispose()
        logger.info("应用已关闭")

# 创建 FastAPI 应用实例
app = FastAPI(lifespan=lifespan)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定义尺码排序顺序
SIZE_ORDER = ['100','110','120','130','140','150','XS','S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL','6XL','7XL','8XL','9XL','10XL']

# Pydantic 模型用于数据验证
from pydantic import BaseModel

class InputData(BaseModel):
    data: List[List[Union[str, int]]]
    rows_per_column: int

def clean_and_order_size(size):
    try:
        size = str(size).upper().strip()
        
        if size in SIZE_ORDER:
            return SIZE_ORDER.index(size)
        
        if size.endswith('XL'):
            x_count = size.count('X')
            if x_count > 0:
                xl_number = max(1, x_count)
                converted_size = f'{xl_number}XL'
                if converted_size in SIZE_ORDER:
                    return SIZE_ORDER.index(converted_size)
        
        if size[:-2].isdigit() and size.endswith('XL'):
            xl_number = int(size[:-2])
            converted_size = f'{xl_number}XL'
            if converted_size in SIZE_ORDER:
                return SIZE_ORDER.index(converted_size)
        
        return len(SIZE_ORDER)
    except Exception as e:
        logger.error(f"尺码处理错误: {str(e)}")
        return len(SIZE_ORDER)

def convert_size(size):
    try:
        size = str(size).upper().strip()
        if size.endswith('XL'):
            x_count = size.count('X')
            if x_count > 1:
                return f'{x_count}XL'
        return size
    except Exception as e:
        logger.error(f"尺码转换错误: {str(e)}")
        return str(size)

@app.get("/")
async def root():
    return {"message": "欢迎使用尺码排序API"}

@app.get("/test-db")
async def test_db():
    try:
        async with get_session() as session:
            await session.execute("SELECT 1")
            return {"message": "数据库连接成功"}
    except Exception as e:
        logger.error(f"数据库连接测试失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-data")
async def process_data(input_data: InputData):
    try:
        logger.info(f"接收到数据处理请求")
        
        if not input_data.data or len(input_data.data) < 2:
            raise ValueError("数据为空或少于2行（包括表头）")

        # 数据预处理和验证
        data = [[str(cell) for cell in row] for row in input_data.data]
        logger.info(f"数据预处理完成，第一行: {data[0]}")
        
        df = pd.DataFrame(data[1:], columns=data[0])
        
        if len(df.columns) < 2:
            raise ValueError(f"数据应至少包含2列。当前列数: {len(df.columns)}")

        # 数据处理
        df = df.iloc[:, :2]
        df.columns = ['姓名', '尺码']

        df['转换尺码'] = df['尺码'].apply(convert_size)
        df['尺码排序'] = df['转换尺码'].apply(clean_and_order_size)
        df['姓名长度'] = df['姓名'].str.len()
        df = df.sort_values(['尺码排序', '姓名长度', '姓名'])
        df = df.drop(['尺码排序', '姓名长度'], axis=1)

        df['序号'] = range(1, len(df) + 1)
        df = df[['序号', '姓名', '转换尺码']]
        df = df.rename(columns={'转换尺码': '尺码'})

        # 保存到数据库
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text(f"TRUNCATE TABLE {SizeRecord.__tablename__} RESTART IDENTITY"))
            
            for _, row in df.iterrows():
                record = SizeRecord(
                    序号=row['序号'],
                    姓名=row['姓名'],
                    尺码=row['尺码']
                )
                session.add(record)
            
            await session.commit()
            logger.info("数据已成功保存到数据库")

        processed_data = df.values.tolist()
        processed_data.insert(0, df.columns.tolist())

        return {
            "processed_data": processed_data,
            "rows_per_column": input_data.rows_per_column
        }

    except ValueError as ve:
        logger.error(f"数据处理值错误: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"数据处理错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get-records")
async def get_records():
    try:
        async with get_session() as session:
            result = await session.execute(
                select(SizeRecord).order_by(SizeRecord.序号)
            )
            records = result.scalars().all()
            return {"records": [
                {
                    "id": record.id,
                    "序号": record.序号,
                    "姓名": record.姓名,
                    "尺码": record.尺码,
                    "创建时间": record.创建时间.isoformat()
                }
                for record in records
            ]}
    except Exception as e:
        logger.error(f"获取记录错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{format}")
async def download_file(format: str):
    try:
        async with get_session() as session:
            result = await session.execute(
                select(SizeRecord).order_by(SizeRecord.序号)
            )
            records = result.scalars().all()
            
            data = [["序号", "姓名", "尺码"]]
            for record in records:
                data.append([record.序号, record.姓名, record.尺码])

            if format == "csv":
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerows(data)
                output.seek(0)
                
                return StreamingResponse(
                    iter([output.getvalue()]),
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=size_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
                )
                
            elif format == "excel":
                wb = Workbook()
                ws = wb.active
                ws.title = "尺码记录"

                # 设置列宽
                ws.column_dimensions['A'].width = 8
                ws.column_dimensions['B'].width = 15
                ws.column_dimensions['C'].width = 8

                # 设置样式
                header_font = Font(bold=True)
                cell_alignment = Alignment(horizontal='center', vertical='center')
                border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )

                # 写入数据并应用样式
                for row in data:
                    ws.append(row)

                for row in ws.iter_rows(min_row=1, max_row=len(data), min_col=1, max_col=3):
                    for cell in row:
                        cell.alignment = cell_alignment
                        cell.border = border
                        if cell.row == 1:
                            cell.font = header_font

                excel_file = io.BytesIO()
                wb.save(excel_file)
                excel_file.seek(0)

                return StreamingResponse(
                    iter([excel_file.getvalue()]),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=size_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
                )
            else:
                raise HTTPException(status_code=400, detail="不支持的文件格式")
    except Exception as e:
        logger.error(f"下载文件错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("启动服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000)