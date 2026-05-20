import asyncio
import asyncpg
import io

async def export_table_to_csv(db_pool, table_name):
    # Use BytesIO directly so asyncpg can write raw bytes to it
    buffer = io.BytesIO()
        
    async with db_pool.acquire() as conn:
        await conn.copy_from_query(
            f"SELECT * FROM {table_name}", 
            output=buffer, 
            format='csv', 
            header=True
        )
    
    # Reset buffer to the beginning so Telegram can read it
    buffer.seek(0)
    
    # Name the buffer (sometimes Telegram gets picky if the file object lacks a name)
    buffer.name = f"{table_name}.csv"
    
    return buffer

