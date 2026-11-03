from flask import Flask, request, redirect, session, jsonify, send_from_directory, render_template_string
import sqlite3, os, csv, io, re, math, secrets, urllib.request, urllib.parse, json as json_lib
from datetime import timedelta
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.environ.get('FINPILOT_SECRET') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('FINPILOT_COOKIE_SECURE','0')=='1', PERMANENT_SESSION_LIFETIME=timedelta(days=14), MAX_CONTENT_LENGTH=12*1024*1024)
BASE=os.path.dirname(os.path.abspath(__file__)); DB=os.environ.get('FINPILOT_DB',os.path.join(BASE,'finpilot.db'))
def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init_db():
 c=db()
 c.executescript('''
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,amount REAL NOT NULL,type TEXT NOT NULL,date TEXT NOT NULL,notes TEXT DEFAULT '',source TEXT DEFAULT 'manual',created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS budgets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,category TEXT NOT NULL,amount REAL NOT NULL,month TEXT NOT NULL,UNIQUE(user_id,category,month),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,target REAL NOT NULL,saved REAL NOT NULL DEFAULT 0,deadline TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS goal_contributions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,goal_id INTEGER NOT NULL,amount REAL NOT NULL,date TEXT NOT NULL,note TEXT DEFAULT '',FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,provider TEXT DEFAULT '',amount REAL NOT NULL,due_date TEXT NOT NULL,frequency TEXT DEFAULT 'Once',status TEXT DEFAULT 'Upcoming',category TEXT DEFAULT 'Bills',type TEXT DEFAULT 'expense',notes TEXT DEFAULT '',transaction_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE SET NULL);
 CREATE TABLE IF NOT EXISTS investments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,asset_type TEXT NOT NULL,asset_name TEXT NOT NULL,symbol TEXT DEFAULT '',quantity REAL NOT NULL,buy_price REAL NOT NULL,current_price REAL NOT NULL,purchase_date TEXT NOT NULL,notes TEXT DEFAULT '',quote_source TEXT DEFAULT 'manual',price_updated_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS investment_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,investment_id INTEGER NOT NULL,action TEXT NOT NULL,quantity REAL NOT NULL,price REAL NOT NULL,amount REAL NOT NULL,notes TEXT DEFAULT '',date TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(investment_id) REFERENCES investments(id) ON DELETE CASCADE);
 ''')
 # additive compatibility for earlier FinPilot DB
 for table, cols in {'transactions':[('notes',"TEXT DEFAULT ''"),('source',"TEXT DEFAULT 'manual'"),('created_at','TEXT')], 'users':[('created_at','TEXT')], 'budgets':[('month',"TEXT DEFAULT '"+date.today().strftime('%Y-%m')+"'")], 'goals':[('deadline','TEXT'),('created_at','TEXT')], 'bills':[('type',"TEXT DEFAULT 'expense'")], 'investments':[('notes',"TEXT DEFAULT ''"),('quote_source',"TEXT DEFAULT 'manual'"),('price_updated_at','TEXT')]}.items():
  have={r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
  for col,typ in cols:
   if col not in have: c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
 c.commit(); c.close()
def uid(): return session.get('user_id')
def auth(): return uid() is not None
def err(msg,code=400): return jsonify(success=False,message=msg),code
def page(name):
 if not auth(): return redirect('/login')
 return send_from_directory(BASE,name)
def money(v):
 try:
  n=float(v or 0); return round(n,2) if math.isfinite(n) else 0.0
 except (TypeError,ValueError): return 0.0
@app.errorhandler(413)
def too_large(_): return err('Upload is too large. Please use an image under 10 MB.',413)
@app.route('/')
def home(): return redirect('/dashboard' if auth() else '/login')
@app.route('/<path:filename>')
def files(filename):
 if filename.endswith('.html') and filename not in ('login.html','register.html'): 
  if not auth(): return redirect('/login')
 return send_from_directory(BASE,filename)
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='GET': return send_from_directory(BASE,'login.html')
 d=request.get_json(silent=True) or request.form; email=str(d.get('email','')).strip().lower(); pw=str(d.get('password',''))
 c=db(); u=c.execute('SELECT * FROM users WHERE lower(email)=?',(email,)).fetchone(); c.close()
 if not u or not check_password_hash(u['password'],pw): return err('Email or password is incorrect.',401)
 session.clear(); session.permanent=True; session['user_id']=u['id']; session['name']=u['name']; return jsonify(success=True,redirect='/dashboard')
@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='GET': return send_from_directory(BASE,'register.html')
 d=request.get_json(silent=True) or request.form; name=str(d.get('name','')).strip(); email=str(d.get('email','')).strip().lower(); pw=str(d.get('password',''))
 if not name or not email or len(pw)<6: return err('Enter your name, a valid email, and a password of at least 6 characters.')
 c=db()
 try:
  cur=c.execute('INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)',(name,email,generate_password_hash(pw),datetime.now().isoformat(timespec='seconds'))); c.commit(); session.clear(); session.permanent=True; session['user_id']=cur.lastrowid; session['name']=name
 except sqlite3.IntegrityError: c.close(); return err('An account with this email already exists.')
 c.close(); return jsonify(success=True,redirect='/dashboard')
@app.route('/logout')
def logout(): session.clear(); return redirect('/login')
@app.route('/dashboard')
def dashboard(): return page('dashboard.html')
@app.route('/budget')
def budget_page(): return page('budget.html')
@app.route('/goals')
def goals_page(): return page('goals.html')
@app.route('/bills')
def bills_page(): return page('bills.html')
@app.route('/reports')
def reports_page(): return page('reports.html')
@app.route('/investments')
def investments_page(): return page('investment.html')
@app.route('/api/user')
def api_user():
 if not auth(): return err('Login required',401)
 return jsonify(success=True,user={'id':uid(),'name':session.get('name','')})
@app.route('/api/dashboard')
def api_dashboard():
 if not auth(): return err('Login required',401)
 period=request.args.get('period','all')
 c=db(); m=date.today().strftime('%Y-%m')
 all_rows=c.execute("SELECT type,COALESCE(SUM(amount),0) n FROM transactions WHERE user_id=? GROUP BY type",(uid(),)).fetchall()
 month_rows=c.execute("SELECT type,COALESCE(SUM(amount),0) n FROM transactions WHERE user_id=? AND substr(date,1,7)=? GROUP BY type",(uid(),m)).fetchall()
 all_totals={r['type']:money(r['n']) for r in all_rows}; month_totals={r['type']:money(r['n']) for r in month_rows}
 recent=c.execute('SELECT * FROM transactions WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 8',(uid(),)).fetchall()
 goals=c.execute('SELECT * FROM goals WHERE user_id=? ORDER BY id DESC',(uid(),)).fetchall()
 inv=c.execute('SELECT COALESCE(SUM(quantity*current_price),0) val,COALESCE(SUM(quantity*buy_price),0) cost FROM investments WHERE user_id=?',(uid(),)).fetchone()
 budgets=c.execute('SELECT COALESCE(SUM(amount),0) total FROM budgets WHERE user_id=? AND month=?',(uid(),m)).fetchone()['total']
 spend_sql="SELECT category,COALESCE(SUM(amount),0) amount FROM transactions WHERE user_id=? AND type='expense'"
 args=[uid()]
 if period=='month': spend_sql+=' AND substr(date,1,7)=?'; args.append(m)
 spend_sql+=' GROUP BY category ORDER BY amount DESC'
 categories=[dict(r) for r in c.execute(spend_sql,args).fetchall()]
 month_spent=month_totals.get('expense',0); month_income=month_totals.get('income',0); month_savings=month_income-month_spent
 all_income=all_totals.get('income',0); all_expense=all_totals.get('expense',0)
 budget_total=money(budgets); budget_percent=min(100,month_spent/budget_total*100) if budget_total else 0
 savings_rate=(month_savings/month_income*100) if month_income else 0
 # Transparent heuristic for the dashboard: savings rate, budget adherence, and goal progress.
 savings_score=max(0,min(40,40*(savings_rate/20))) if month_income else 0
 budget_score=(30 if budget_total and month_spent<=budget_total else max(0,30*(budget_total/month_spent))) if month_spent else 30
 goal_score=30*(sum(min(1,g['saved']/g['target']) for g in goals)/len(goals)) if goals else 15
 score=int(max(0,min(100,savings_score+budget_score+goal_score)))
 label='Excellent' if score>=80 else 'Good' if score>=60 else 'Building habits' if score>=40 else 'Getting started'
 message='Strong savings and budget habits are showing.' if score>=80 else 'Keep tracking consistently and build your monthly savings.' if score>=50 else 'Record income, expenses, and a realistic budget to build your baseline.'
 c.close()
 summary={'total_income':all_income,'total_expenses':all_expense,'total_balance':all_income-all_expense,'month_income':month_income,'month_expenses':month_spent,'month_savings':month_savings,'savings_rate':savings_rate,'budget_total':budget_total,'budget_spent':month_spent,'budget_remaining':budget_total-month_spent,'budget_percent':budget_percent,'financial_score':score,'financial_label':label,'financial_message':message}
 return jsonify(success=True,month=m,summary=summary,income=month_income,expenses=month_spent,balance=month_savings,investment_value=money(inv['val']),investment_gain=money(inv['val']-inv['cost']),transactions=[dict(r) for r in recent],goals=[dict(r) for r in goals],categories=categories)
@app.route('/api/transactions',methods=['GET','POST'])
def transactions():
 if not auth(): return err('Login required',401)
 c=db()
 if request.method=='GET':
  month=request.args.get('month',''); typ=request.args.get('type',''); q=request.args.get('q','').strip(); sql='SELECT * FROM transactions WHERE user_id=?'; args=[uid()]
  if month: sql+=' AND substr(date,1,7)=?'; args.append(month)
  if typ in ('income','expense'): sql+=' AND type=?'; args.append(typ)
  if q: sql+=' AND (name LIKE ? OR category LIKE ? OR notes LIKE ?)'; args += [f'%{q}%']*3
  rows=c.execute(sql+' ORDER BY date DESC,id DESC',args).fetchall(); c.close(); return jsonify(success=True,transactions=[dict(r) for r in rows])
 d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); category=str(d.get('category','Other')).strip() or 'Other'; typ=str(d.get('type','expense')).lower(); dt=str(d.get('date') or date.today().isoformat()); notes=str(d.get('notes',''))
 try: amount=float(d.get('amount',0))
 except (TypeError,ValueError): amount=0
 try: date.fromisoformat(dt)
 except ValueError: c.close(); return err('Enter a valid transaction date.')
 if not name or not math.isfinite(amount) or amount<=0 or amount>1_000_000_000 or typ not in ('income','expense'): c.close(); return err('Enter a description, valid positive amount, and income or expense type.')
 cur=c.execute('INSERT INTO transactions(user_id,name,category,amount,type,date,notes,source,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid(),name,category,amount,typ,dt,notes,str(d.get('source','manual')),datetime.now().isoformat(timespec='seconds'))); c.commit(); row=c.execute('SELECT * FROM transactions WHERE id=?',(cur.lastrowid,)).fetchone(); c.close(); return jsonify(success=True,transaction=dict(row))
@app.route('/api/transactions/<int:tid>',methods=['DELETE'])
def delete_transaction(tid):
 if not auth(): return err('Login required',401)
 c=db(); c.execute('DELETE FROM transactions WHERE id=? AND user_id=?',(tid,uid())); c.commit(); c.close(); return jsonify(success=True)
@app.route('/api/budgets',methods=['GET','POST'])
def budgets():
 if not auth(): return err('Login required',401)
 c=db()
 if request.method=='GET':
  month=request.args.get('month',date.today().strftime('%Y-%m')); rows=c.execute('SELECT * FROM budgets WHERE user_id=? AND month=? ORDER BY category',(uid(),month)).fetchall(); spent=c.execute("SELECT category,SUM(amount) amount FROM transactions WHERE user_id=? AND type='expense' AND substr(date,1,7)=? GROUP BY category",(uid(),month)).fetchall(); c.close(); return jsonify(success=True,budgets=[dict(r) for r in rows],spent={r['category']:money(r['amount']) for r in spent},month=month)
 d=request.get_json(silent=True) or {}; cat=str(d.get('category','')).strip(); month=str(d.get('month') or date.today().strftime('%Y-%m'))
 try: amount=float(d.get('amount',0))
 except: amount=0
 if not cat or amount<=0: c.close(); return err('Choose a category and enter a budget greater than zero.')
 c.execute('INSERT INTO budgets(user_id,category,amount,month) VALUES(?,?,?,?) ON CONFLICT(user_id,category,month) DO UPDATE SET amount=excluded.amount',(uid(),cat,amount,month)); c.commit(); c.close(); return jsonify(success=True)
@app.route('/api/goals',methods=['GET','POST'])
def goals():
 if not auth(): return err('Login required',401)
 c=db()
 if request.method=='GET': rows=c.execute('SELECT * FROM goals WHERE user_id=? ORDER BY id DESC',(uid(),)).fetchall(); c.close(); return jsonify(success=True,goals=[dict(r) for r in rows])
 d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip(); deadline=d.get('deadline') or None
 try: target=float(d.get('target',0)); saved=max(0,float(d.get('saved',0)))
 except: target=saved=0
 if not name or target<=0: c.close(); return err('Goal name and target amount are required.')
 cur=c.execute('INSERT INTO goals(user_id,name,target,saved,deadline,created_at) VALUES(?,?,?,?,?,?)',(uid(),name,target,saved,deadline,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close(); return jsonify(success=True,id=cur.lastrowid)
@app.route('/api/goals/<int:gid>',methods=['PATCH','DELETE'])
def goal_item(gid):
 if not auth(): return err('Login required',401)
 c=db()
 if request.method=='DELETE': c.execute('DELETE FROM goals WHERE id=? AND user_id=?',(gid,uid())); c.commit(); c.close(); return jsonify(success=True)
 d=request.get_json(silent=True) or {}; name=str(d.get('name','')).strip()
 try: target=float(d.get('target',0)); saved=max(0,float(d.get('saved',0)))
 except: target=saved=0
 if not name or target<=0: c.close(); return err('Name and target are required.')
 c.execute('UPDATE goals SET name=?,target=?,saved=?,deadline=? WHERE id=? AND user_id=?',(name,target,saved,d.get('deadline') or None,gid,uid())); c.commit(); c.close(); return jsonify(success=True)
@app.route('/api/goals/<int:gid>/contributions',methods=['POST'])
def goal_contribution(gid):
 if not auth(): return err('Login required',401)
 d=request.get_json(silent=True) or {}
 try: amount=float(d.get('amount',0))
 except: amount=0
 if amount<=0: return err('Contribution must be greater than zero.')
 c=db(); g=c.execute('SELECT * FROM goals WHERE id=? AND user_id=?',(gid,uid())).fetchone()
 if not g: c.close(); return err('Goal not found.',404)
 c.execute('UPDATE goals SET saved=saved+? WHERE id=? AND user_id=?',(amount,gid,uid())); c.execute('INSERT INTO goal_contributions(user_id,goal_id,amount,date,note) VALUES(?,?,?,?,?)',(uid(),gid,amount,str(d.get('date') or date.today().isoformat()),str(d.get('note','')))); c.commit(); c.close(); return jsonify(success=True)
@app.route('/api/receipts',methods=['POST'])
def save_receipt():
 if not auth(): return err('Login required',401)
 d=request.get_json(silent=True) or {}
 name=str(d.get('name','')).strip()[:180]
 category=str(d.get('category','Other')).strip()[:80] or 'Other'
 typ=str(d.get('type','expense')).lower()
 dt=str(d.get('date') or date.today().isoformat())
 notes=str(d.get('notes','')).strip()[:12000]
 try: amount=float(d.get('amount',0))
 except (TypeError,ValueError): amount=0
 try: date.fromisoformat(dt)
 except ValueError: return err('Enter a valid receipt date.')
 if not name or not math.isfinite(amount) or not (0 < amount <= 1_000_000_000) or typ not in ('income','expense'):
  return err('Review the description, positive amount, and transaction type.')
 c=db()
 try:
  cur=c.execute('INSERT INTO transactions(user_id,name,category,amount,type,date,notes,source,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid(),name,category,amount,typ,dt,notes,'receipt',datetime.now().isoformat(timespec='seconds')))
  txid=cur.lastrowid
  if d.get('save_as_bill'):
   frequency=str(d.get('frequency','Once'))
   if frequency not in ('Once','Weekly','Monthly','Quarterly','Yearly'): frequency='Once'
   c.execute('INSERT INTO bills(user_id,title,provider,amount,due_date,frequency,status,category,type,notes,transaction_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid(),name,str(d.get('provider',''))[:180],amount,dt,frequency,'Paid',category,typ,notes,txid))
   if frequency != 'Once':
    paid_date=date.fromisoformat(dt)
    if frequency=='Weekly': next_date=paid_date+timedelta(days=7)
    elif frequency=='Quarterly': next_date=paid_date+timedelta(days=90)
    elif frequency=='Yearly':
     try: next_date=paid_date.replace(year=paid_date.year+1)
     except ValueError: next_date=paid_date.replace(year=paid_date.year+1,day=28)
    else:
     month=paid_date.month%12+1; year=paid_date.year+(1 if paid_date.month==12 else 0)
     day=min(paid_date.day,[31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
     next_date=date(year,month,day)
    c.execute('INSERT INTO bills(user_id,title,provider,amount,due_date,frequency,status,category,type,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),name,str(d.get('provider',''))[:180],amount,next_date.isoformat(),frequency,'Upcoming',category,typ,notes))
  c.commit()
 except Exception:
  c.rollback(); c.close(); return err('Receipt could not be saved. Please try again.',500)
 row=c.execute('SELECT * FROM transactions WHERE id=? AND user_id=?',(txid,uid())).fetchone(); c.close()
 return jsonify(success=True,transaction=dict(row))

@app.route('/api/bills',methods=['GET','POST'])
def bills():
 if not auth(): return err('Login required',401)
 c=db()
 if request.method=='GET': rows=c.execute('SELECT * FROM bills WHERE user_id=? ORDER BY due_date,id',(uid(),)).fetchall(); c.close(); return jsonify(success=True,bills=[dict(r) for r in rows])
 d=request.get_json(silent=True) or {}; title=str(d.get('title','')).strip(); provider=str(d.get('provider','')).strip(); category=str(d.get('category','Bills')); freq=str(d.get('frequency','Once')); status=str(d.get('status','Upcoming')); dt=str(d.get('due_date') or date.today().isoformat()); typ=str(d.get('type','expense'))
 try: amount=float(d.get('amount',0))
 except: amount=0
 try: date.fromisoformat(dt)
 except ValueError: c.close(); return err('Enter a valid bill due date.')
 if not title or not math.isfinite(amount) or amount<=0 or amount>1_000_000_000: c.close(); return err('Bill name and a valid positive amount are required.')
 c.execute('INSERT INTO bills(user_id,title,provider,amount,due_date,frequency,status,category,type,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),title,provider,amount,dt,freq,status,category,str(d.get('type','expense')),str(d.get('notes',d.get('ocr_text',''))))); c.commit(); bid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.close(); return jsonify(success=True,id=bid)
@app.route('/api/bills/<int:bid>',methods=['PATCH','DELETE'])
def bill_item(bid):
 if not auth(): return err('Login required',401)
 c=db(); b=c.execute('SELECT * FROM bills WHERE id=? AND user_id=?',(bid,uid())).fetchone()
 if not b: c.close(); return err('Bill not found',404)
 if request.method=='DELETE': c.execute('DELETE FROM bills WHERE id=? AND user_id=?',(bid,uid())); c.commit(); c.close(); return jsonify(success=True)
 d=request.get_json(silent=True) or {}; status=str(d.get('status','Paid'))
 if status=='Paid' and b['status']!='Paid':
  cur=c.execute('INSERT INTO transactions(user_id,name,category,amount,type,date,notes,source,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid(),b['title'],b['category'],b['amount'],b['type'] or 'expense',b['due_date'],'Paid bill: '+(b['provider'] or b['title']),'bill',datetime.now().isoformat(timespec='seconds')))
  c.execute('UPDATE bills SET status=?,transaction_id=? WHERE id=? AND user_id=?',(status,cur.lastrowid,bid,uid()))
  if b['frequency']!='Once':
   due=datetime.strptime(b['due_date'],'%Y-%m-%d').date()
   if b['frequency']=='Weekly': nxt=due+timedelta(days=7)
   elif b['frequency']=='Quarterly': nxt=(due+timedelta(days=90))
   elif b['frequency']=='Yearly': nxt=due.replace(year=due.year+1)
   else:
    month=due.month%12+1; year=due.year+(1 if due.month==12 else 0); day=min(due.day,[31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1]); nxt=date(year,month,day)
   c.execute('INSERT INTO bills(user_id,title,provider,amount,due_date,frequency,status,category,type,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),b['title'],b['provider'],b['amount'],nxt.isoformat(),b['frequency'],'Upcoming',b['category'],b['notes']))
 else: c.execute('UPDATE bills SET status=? WHERE id=? AND user_id=?',(status,bid,uid()))
 c.commit(); c.close(); return jsonify(success=True)
@app.route('/api/reports')
def reports():
 if not auth(): return err('Login required',401)
 month=request.args.get('month',date.today().strftime('%Y-%m')); c=db(); rows=c.execute('SELECT type,category,SUM(amount) amount FROM transactions WHERE user_id=? AND substr(date,1,7)=? GROUP BY type,category',(uid(),month)).fetchall(); daily=c.execute('SELECT date,type,SUM(amount) amount FROM transactions WHERE user_id=? AND substr(date,1,7)=? GROUP BY date,type ORDER BY date',(uid(),month)).fetchall(); c.close(); return jsonify(success=True,month=month,category_totals=[dict(r) for r in rows],daily=[dict(r) for r in daily])
@app.route('/api/reports.csv')
def reports_csv():
 if not auth(): return err('Login required',401)
 month=request.args.get('month',date.today().strftime('%Y-%m')); c=db(); rows=c.execute('SELECT date,type,name,category,amount,notes FROM transactions WHERE user_id=? AND substr(date,1,7)=? ORDER BY date',(uid(),month)).fetchall(); c.close(); out=io.StringIO(); w=csv.writer(out); w.writerow(['Date','Type','Description','Category','Amount','Notes']); w.writerows([tuple(r) for r in rows]); from flask import Response; return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=finpilot-{month}.csv'})
# ─── Investments ─────────────────────────────────────────────────────────────
ASSET_CATALOG = [
  {"asset_type":"Stocks","asset_name":"Reliance Industries","symbol":"RELIANCE.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Tata Consultancy Services","symbol":"TCS.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"HDFC Bank","symbol":"HDFCBANK.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Infosys","symbol":"INFY.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"ICICI Bank","symbol":"ICICIBANK.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"State Bank of India","symbol":"SBIN.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Bharti Airtel","symbol":"BHARTIARTL.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"ITC","symbol":"ITC.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Larsen & Toubro","symbol":"LT.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Axis Bank","symbol":"AXISBANK.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Bajaj Finance","symbol":"BAJFINANCE.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Hindustan Unilever","symbol":"HINDUNILVR.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Kotak Mahindra Bank","symbol":"KOTAKBANK.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Maruti Suzuki","symbol":"MARUTI.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Asian Paints","symbol":"ASIANPAINT.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Sun Pharmaceutical","symbol":"SUNPHARMA.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Titan Company","symbol":"TITAN.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Wipro","symbol":"WIPRO.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"UltraTech Cement","symbol":"ULTRACEMCO.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Nestle India","symbol":"NESTLEIND.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Power Grid","symbol":"POWERGRID.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"NTPC","symbol":"NTPC.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Tata Motors","symbol":"TATAMOTORS.NS","quote_source":"yahoo"},
  {"asset_type":"Stocks","asset_name":"Adani Enterprises","symbol":"ADANIENT.NS","quote_source":"yahoo"},
  {"asset_type":"Mutual Funds","asset_name":"Nippon India Nifty 50 ETF","symbol":"NIFTYBEES.NS","quote_source":"yahoo"},
  {"asset_type":"Mutual Funds","asset_name":"ICICI Prudential Nifty ETF","symbol":"ICICINIFTY.NS","quote_source":"yahoo"},
  {"asset_type":"Gold","asset_name":"Gold (manual INR price)","symbol":"","quote_source":"manual"},
  {"asset_type":"Silver","asset_name":"Silver (manual INR price)","symbol":"","quote_source":"manual"},
  {"asset_type":"Crypto","asset_name":"Bitcoin","symbol":"BTC-USD","quote_source":"yahoo"},
  {"asset_type":"Crypto","asset_name":"Ethereum","symbol":"ETH-USD","quote_source":"yahoo"},
]

def _inv_row(r):
  x=dict(r)
  qty=float(r['quantity'] or 0); buy=float(r['buy_price'] or 0); cur=float(r['current_price'] or 0)
  x['invested_value']=money(qty*buy); x['current_value']=money(qty*cur); x['gain']=money(x['current_value']-x['invested_value'])
  x['return_pct']=round((x['gain']/x['invested_value']*100) if x['invested_value'] else 0, 2)
  return x

def _fetch_yahoo_price(symbol):
  """Best-effort delayed quote via Yahoo chart API. Returns (price, source_note) or (None, reason)."""
  symbol=(symbol or '').strip()
  if not symbol: return None, 'No symbol'
  url=f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=1d'
  try:
    req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 FinPilot/1.0'})
    with urllib.request.urlopen(req, timeout=8) as resp:
      payload=json_lib.loads(resp.read().decode())
    result=(payload.get('chart') or {}).get('result') or []
    if not result: return None, 'No quote data'
    meta=result[0].get('meta') or {}
    price=meta.get('regularMarketPrice') or meta.get('previousClose')
    currency=meta.get('currency') or ''
    if price is None: return None, 'Price unavailable'
    return float(price), f'yahoo delayed ({currency})'
  except Exception as e:
    return None, f'Quote failed: {type(e).__name__}'

@app.route('/api/investments/catalog')
def investment_catalog():
  if not auth(): return err('Login required',401)
  q=str(request.args.get('q','')).strip().lower()
  items=ASSET_CATALOG
  if q:
    items=[a for a in items if q in a['asset_name'].lower() or q in a['symbol'].lower() or q in a['asset_type'].lower()]
  return jsonify(success=True, results=items[:20])

@app.route('/api/investments/quote')
def investment_quote():
  if not auth(): return err('Login required',401)
  symbol=str(request.args.get('symbol','')).strip()
  if not symbol: return err('Symbol required')
  price, note = _fetch_yahoo_price(symbol)
  if price is None:
    return jsonify(success=False, message=note or 'Could not fetch quote', price=None, source='unavailable')
  return jsonify(success=True, price=round(price,4), source=note, symbol=symbol, fetched_at=datetime.now().isoformat(timespec='seconds'))

@app.route('/api/investments',methods=['GET','POST'])
def investments():
  if not auth(): return err('Login required',401)
  c=db()
  if request.method=='GET':
    rows=c.execute('SELECT * FROM investments WHERE user_id=? ORDER BY id DESC',(uid(),)).fetchall()
    data=[_inv_row(r) for r in rows]
    c.close(); return jsonify(success=True,investments=data)
  d=request.get_json(silent=True) or {}
  typ=str(d.get('asset_type','Other')).strip() or 'Other'
  name=str(d.get('asset_name','')).strip()
  symbol=str(d.get('symbol','')).strip()
  notes=str(d.get('notes','')).strip()
  quote_source=str(d.get('quote_source','manual')).strip() or 'manual'
  dt=str(d.get('purchase_date') or date.today().isoformat())
  try: qty=float(d.get('quantity',0)); buy=float(d.get('buy_price',0)); cur=float(d.get('current_price') or buy)
  except (TypeError,ValueError): qty=buy=cur=0
  try: date.fromisoformat(dt)
  except ValueError: c.close(); return err('Enter a valid purchase date.')
  if not name or qty<=0 or buy<=0 or cur<=0 or not math.isfinite(qty+buy+cur):
    c.close(); return err('Enter asset name, quantity > 0, buy price, and current price.')
  existing=None
  if symbol:
    existing=c.execute('SELECT * FROM investments WHERE user_id=? AND symbol=? AND asset_name=?',(uid(),symbol,name)).fetchone()
  now=datetime.now().isoformat(timespec='seconds')
  if existing:
    old_qty=float(existing['quantity']); old_buy=float(existing['buy_price'])
    new_qty=old_qty+qty
    avg=((old_qty*old_buy)+(qty*buy))/new_qty if new_qty else buy
    c.execute('UPDATE investments SET quantity=?,buy_price=?,current_price=?,price_updated_at=?,quote_source=? WHERE id=? AND user_id=?',
              (new_qty, money(avg), money(cur), now, quote_source, existing['id'], uid()))
    inv_id=existing['id']
  else:
    cur_ins=c.execute('INSERT INTO investments(user_id,asset_type,asset_name,symbol,quantity,buy_price,current_price,purchase_date,notes,quote_source,price_updated_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
              (uid(),typ,name,symbol,qty,money(buy),money(cur),dt,notes,quote_source,now,now))
    inv_id=cur_ins.lastrowid
  c.execute('INSERT INTO investment_transactions(user_id,investment_id,action,quantity,price,amount,notes,date,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (uid(),inv_id,'buy',qty,money(buy),money(qty*buy),notes or 'Initial purchase',dt,now))
  c.commit(); row=c.execute('SELECT * FROM investments WHERE id=?',(inv_id,)).fetchone(); c.close()
  return jsonify(success=True, investment=_inv_row(row))

@app.route('/api/investments/<int:iid>',methods=['PATCH','DELETE'])
def investment_item(iid):
  if not auth(): return err('Login required',401)
  c=db()
  row=c.execute('SELECT * FROM investments WHERE id=? AND user_id=?',(iid,uid())).fetchone()
  if not row: c.close(); return err('Investment not found.',404)
  if request.method=='DELETE':
    c.execute('DELETE FROM investments WHERE id=? AND user_id=?',(iid,uid()))
    c.commit(); c.close(); return jsonify(success=True)
  d=request.get_json(silent=True) or {}
  name=str(d.get('asset_name', row['asset_name'])).strip() or row['asset_name']
  typ=str(d.get('asset_type', row['asset_type'])).strip() or row['asset_type']
  symbol=str(d.get('symbol', row['symbol'] or '')).strip()
  notes=str(d.get('notes', row['notes'] if 'notes' in row.keys() else '') or '')
  try: cur=float(d.get('current_price', row['current_price']))
  except (TypeError,ValueError): cur=float(row['current_price'])
  if cur<=0 or not math.isfinite(cur): c.close(); return err('Current price must be positive.')
  quote_source=str(d.get('quote_source', row['quote_source'] if 'quote_source' in row.keys() else 'manual') or 'manual')
  now=datetime.now().isoformat(timespec='seconds')
  c.execute('UPDATE investments SET asset_name=?,asset_type=?,symbol=?,current_price=?,notes=?,quote_source=?,price_updated_at=? WHERE id=? AND user_id=?',
            (name,typ,symbol,money(cur),notes,quote_source,now,iid,uid()))
  c.commit(); row=c.execute('SELECT * FROM investments WHERE id=?',(iid,)).fetchone(); c.close()
  return jsonify(success=True, investment=_inv_row(row))

@app.route('/api/investments/<int:iid>/buy',methods=['POST'])
def investment_buy(iid):
  if not auth(): return err('Login required',401)
  d=request.get_json(silent=True) or {}
  try: qty=float(d.get('quantity',0)); price=float(d.get('price',0))
  except (TypeError,ValueError): qty=price=0
  if qty<=0 or price<=0 or not math.isfinite(qty+price): return err('Quantity and price must be positive.')
  dt=str(d.get('date') or date.today().isoformat())
  notes=str(d.get('notes','')).strip()
  c=db(); row=c.execute('SELECT * FROM investments WHERE id=? AND user_id=?',(iid,uid())).fetchone()
  if not row: c.close(); return err('Investment not found.',404)
  old_qty=float(row['quantity']); old_buy=float(row['buy_price'])
  new_qty=old_qty+qty
  avg=((old_qty*old_buy)+(qty*price))/new_qty
  now=datetime.now().isoformat(timespec='seconds')
  c.execute('UPDATE investments SET quantity=?,buy_price=?,current_price=?,price_updated_at=? WHERE id=? AND user_id=?',
            (new_qty, money(avg), money(price), now, iid, uid()))
  c.execute('INSERT INTO investment_transactions(user_id,investment_id,action,quantity,price,amount,notes,date,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (uid(),iid,'buy',qty,money(price),money(qty*price),notes or 'Buy more',dt,now))
  c.commit(); row=c.execute('SELECT * FROM investments WHERE id=?',(iid,)).fetchone(); c.close()
  return jsonify(success=True, investment=_inv_row(row))

@app.route('/api/investments/<int:iid>/sell',methods=['POST'])
def investment_sell(iid):
  if not auth(): return err('Login required',401)
  d=request.get_json(silent=True) or {}
  try: qty=float(d.get('quantity',0)); price=float(d.get('price',0))
  except (TypeError,ValueError): qty=price=0
  if qty<=0 or price<=0 or not math.isfinite(qty+price): return err('Quantity and price must be positive.')
  dt=str(d.get('date') or date.today().isoformat())
  notes=str(d.get('notes','')).strip()
  c=db(); row=c.execute('SELECT * FROM investments WHERE id=? AND user_id=?',(iid,uid())).fetchone()
  if not row: c.close(); return err('Investment not found.',404)
  held=float(row['quantity'])
  if qty>held+1e-9: c.close(); return err(f'Cannot sell more than held quantity ({held}).')
  new_qty=held-qty
  now=datetime.now().isoformat(timespec='seconds')
  if new_qty<=1e-9:
    c.execute('INSERT INTO investment_transactions(user_id,investment_id,action,quantity,price,amount,notes,date,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
              (uid(),iid,'sell',qty,money(price),money(qty*price),notes or 'Sell (full)',dt,now))
    c.execute('DELETE FROM investments WHERE id=? AND user_id=?',(iid,uid()))
    inv=None
  else:
    c.execute('UPDATE investments SET quantity=?,current_price=?,price_updated_at=? WHERE id=? AND user_id=?',
              (new_qty, money(price), now, iid, uid()))
    c.execute('INSERT INTO investment_transactions(user_id,investment_id,action,quantity,price,amount,notes,date,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
              (uid(),iid,'sell',qty,money(price),money(qty*price),notes or 'Sell',dt,now))
    inv=_inv_row(c.execute('SELECT * FROM investments WHERE id=?',(iid,)).fetchone())
  c.commit(); c.close()
  return jsonify(success=True, investment=inv, sold=inv is None)

@app.route('/api/investments/<int:iid>/history')
def investment_history(iid):
  if not auth(): return err('Login required',401)
  c=db()
  row=c.execute('SELECT id FROM investments WHERE id=? AND user_id=?',(iid,uid())).fetchone()
  if not row:
    c.close(); return err('Investment not found.',404)
  rows=c.execute('SELECT * FROM investment_transactions WHERE investment_id=? AND user_id=? ORDER BY date DESC, id DESC',(iid,uid())).fetchall()
  c.close(); return jsonify(success=True, history=[dict(r) for r in rows])

@app.route('/api/investments/refresh-prices',methods=['POST'])
def investment_refresh_prices():
  if not auth(): return err('Login required',401)
  c=db()
  rows=c.execute("SELECT * FROM investments WHERE user_id=? AND COALESCE(symbol,'')!=''",(uid(),)).fetchall()
  updated=[]; failed=[]
  now=datetime.now().isoformat(timespec='seconds')
  for r in rows:
    if (r['asset_type'] or '') in ('Gold','Silver'):
      failed.append({'id':r['id'],'symbol':r['symbol'],'reason':'Use manual INR prices for gold/silver.'})
      continue
    price, note = _fetch_yahoo_price(r['symbol'])
    if price is None:
      failed.append({'id':r['id'],'symbol':r['symbol'],'reason':note})
      continue
    c.execute('UPDATE investments SET current_price=?,quote_source=?,price_updated_at=? WHERE id=? AND user_id=?',
              (money(price), note, now, r['id'], uid()))
    updated.append({'id':r['id'],'symbol':r['symbol'],'price':money(price),'source':note})
  c.commit(); c.close()
  return jsonify(success=True, updated=updated, failed=failed, message=f'Updated {len(updated)} quote(s). {len(failed)} skipped or failed.')

@app.route('/api/investments/ai-analysis')
def investment_analysis():
  if not auth(): return err('Login required',401)
  c=db(); rows=c.execute('SELECT asset_type,SUM(quantity*buy_price) cost,SUM(quantity*current_price) val FROM investments WHERE user_id=? GROUP BY asset_type',(uid(),)).fetchall(); c.close()
  if not rows:
    return jsonify(success=True,analysis={'overview':'Add investments to see your portfolio summary.','diversification':'Your portfolio has no recorded asset allocation yet.','risk':'No portfolio risk signal is available without holdings.','performance':'No investment performance data is available yet.','suggestion':'Add your holdings and keep their current prices updated.'})
  total=sum(r['val'] for r in rows); cost=sum(r['cost'] for r in rows); gain=total-cost
  largest=max(rows,key=lambda r:r['val']); concentration=largest['val']/total if total else 0
  names=', '.join(r['asset_type'] for r in rows)
  return jsonify(success=True,analysis={
    'overview':f'Portfolio value: ₹{total:,.2f}. Unrealized {"gain" if gain>=0 else "loss"}: ₹{abs(gain):,.2f}.',
    'diversification':f'Holdings span {len(rows)} asset categories ({names}). Largest category: {largest["asset_type"]} at {concentration:.0%} of value.',
    'risk':'A single category above 70% indicates concentration exposure; this is a simple allocation flag, not a volatility estimate.' if concentration>0.7 else 'No single asset category exceeds 70% of current portfolio value. This does not measure market or issuer risk.',
    'performance':f'Unrealized return: {(gain/cost*100 if cost else 0):.2f}%. Calculated from your recorded buy and current prices.',
    'suggestion':'Update current prices periodically and review whether your asset mix still matches your time horizon. This is informational, not investment advice.'
  })

@app.route('/api/reset',methods=['POST'])
def reset():
  if not auth(): return err('Login required',401)
  c=db()
  for t in ('investment_transactions','goal_contributions','bills','investments','transactions','budgets','goals'):
    try: c.execute(f'DELETE FROM {t} WHERE user_id=?',(uid(),))
    except sqlite3.OperationalError: pass
  c.commit(); c.close(); return jsonify(success=True)

init_db()
if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG','0')=='1')
