import random
import json  
from fastmcp import FastMCP
import sqlite3
import os
import uvicorn
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "expense.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP(name="ExpenseTracker")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date str NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)

def init_categories():  
    if not os.path.exists(CATEGORIES_PATH):
        default_categories = {
            "categories": ["food", "transport", "entertainment", "utilities", "healthcare"]
        }
        with open(CATEGORIES_PATH, "w", encoding="utf-8") as f:
            json.dump(default_categories, f, indent=2)

init_db()
init_categories()  

@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?, ?, ?, ?, ?)",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}

@mcp.tool()
def list_expenses(start_date, end_date):
    """list all expenses within an inclusive date range"""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """SELECT * from expenses 
               where date between ? and ? 
               order by id asc""",
            (start_date, end_date)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

@mcp.tool()
def summarize(start_date, end_date, category=""):
    with sqlite3.connect(DB_PATH) as c:
        query = """
            select category, sum(amount) as total_amount
            from expenses
            where date between ? and ?
        """
        params = [start_date, end_date]
        
        if category:
            query += " AND category=?"
            params.append(category)
        
        query += " group by category order by total_amount asc"

        cur = c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    
@mcp.tool()
def update(
    cid: int,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None
) -> list[dict]:

    """Update an expense.Only provided fields will be updated."""
    with sqlite3.connect(DB_PATH) as c:
        update_fields=[]
        params=[]

        if date is not None:
            update_fields.append("date=?")
            params.append(date)
        if amount is not None:
            update_fields.append("amount=?")
            params.append(amount)
        if category is not None:
            update_fields.append("category=?")
            params.append(category)
        if subcategory is not None:
            update_fields.append("subcategory=?")
            params.append(subcategory)
        if note is not None:
            update_fields.append("note=?")
            params.append(note)
        
        if not update_fields:
            return {"No fields provided to update"}
        
        params.append(cid)

        query=f"UPDATE expenses SET {', '.join(update_fields)} WHERE id=?"
        c.execute(query,params)
        c.commit()

        select_query="select * from expenses where id=?"
        cur=c.execute(select_query,[cid])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        
        if rows:
            return [dict(zip(cols, r)) for r in rows]
        else:
            return {"error": f"No expense found with id {cid}"}
@mcp.tool()
def delete(
    id: Optional[int] = None,
    date: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    amount: Optional[float] = None,
    note: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> dict:
    """
    Delete expenses based on any column criteria.
    like id,date,category,subcategory,amount,note,start_date,end_date
    
    """
    with sqlite3.connect(DB_PATH) as c:
        conditions = []
        params = []
        
        # Handle date range separately
        if start_date is not None and end_date is not None:
            conditions.append("date BETWEEN ? AND ?")
            params.extend([start_date, end_date])
        elif start_date is not None or end_date is not None:
            return {
                "status": "error",
                "message": "Both start_date and end_date must be provided for date range"
            }
        
        # Handle individual column filters
        if id is not None:
            conditions.append("id = ?")
            params.append(id)
        
        if date is not None:
            conditions.append("date = ?")
            params.append(date)
        
        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        
        if subcategory is not None:
            conditions.append("subcategory = ?")
            params.append(subcategory)
        
        if amount is not None:
            conditions.append("amount = ?")
            params.append(amount)
        
        if note is not None:
            conditions.append("note = ?")
            params.append(note)
        
        
        if not conditions:
            return {
                "status": "error",
                "message": "At least one filter parameter must be provided"
            }
        
        
        query = "DELETE FROM expenses WHERE " + " AND ".join(conditions)
        
        cur = c.execute(query, params)
        c.commit()
        
        deleted_count = cur.rowcount
        
        if deleted_count > 0:
            return {
                "status": "success",
                "message": f"Successfully deleted {deleted_count} expense(s)",
                "deleted_count": deleted_count,
                "criteria": {k: v for k, v in {
                    "id": id,
                    "date": date,
                    "category": category,
                    "subcategory": subcategory,
                    "amount": amount,
                    "note": note,
                    "start_date": start_date,
                    "end_date": end_date
                }.items() if v is not None}
            }
        else:
            return {
                "status": "warning",
                "message": "No expenses found matching the criteria",
                "deleted_count": 0
            }
    
@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    """Get available expense categories"""
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:  # ← FIXED: CATEGORIES_PATH
            return json.load(f)
    except FileNotFoundError:
        return {"categories": [], "error": "categories.json not found"}
    except json.JSONDecodeError:
        return {"categories": [], "error": "Invalid JSON"}
    except Exception:
        return "some error occured"
    
# mcp_app = mcp.http_app(path='/mcp')

# app = FastAPI(title="ExpenseTracker", lifespan=mcp_app.lifespan)

# # Mount the MCP server
# app.mount("/mcp_to_fastapi", mcp_app)

# @app.get("/")
# def home():
#     return {"message":"Welcom to Expense Tracker"}

if __name__ == "__main__":
    mcp.run(transport="http",host="0.0.0.0",port=8000)
