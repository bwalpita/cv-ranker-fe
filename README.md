# 🎨 Frontend UI - Railway Deployment

Gradio interface for CV Ranking System

---

## 🚀 Quick Deploy

### Step 1: Deploy Backend First

**⚠️ IMPORTANT:** Deploy the backend first and get its URL!

See: `../railway_backend/README.md`

### Step 2: Push to GitHub
```bash
cd railway_frontend
git init
git add .
git commit -m "Frontend UI deployment"
git remote add origin <your-frontend-repo-url>
git push -u origin main
```

### Step 3: Deploy on Railway
1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub
3. Select this repository
4. Railway auto-deploys ✅

### Step 4: Configure Environment Variables

In Railway Dashboard → Variables, add:

```bash
# ⚠️ REPLACE with your actual backend URL from Step 1
RANKER_API=https://your-backend-app.up.railway.app/rank/enhanced
API_URL=https://your-backend-app.up.railway.app
QUESTION_API_URL=https://your-backend-app.up.railway.app/ask_flowise

# Gradio Settings
GRADIO_SERVER_NAME=0.0.0.0

# Application Settings (optional)
MAX_FILE_SIZE_MB=10
ALLOWED_FILE_TYPES=pdf,docx,txt
DATABASE_PATH=./data_storage/search_history.db
API_TIMEOUT=30
MAX_SEARCH_HISTORY=5
SOCIAL_PROFILE_VALIDATION=strict

# Python
PYTHONUNBUFFERED=1
```

### Step 5: Access Your App

After deployment:
```
https://your-frontend-app.up.railway.app/
```

---

## 🌐 How It Works

```
┌─────────────────────┐
│   User Browser      │
│                     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Frontend (Gradio)                  │
│  https://your-frontend.railway.app  │
│                                     │
│  • Upload CVs                       │
│  • Enter job descriptions           │
│  • View rankings                    │
│  • Export reports                   │
└──────────┬──────────────────────────┘
           │ HTTP POST
           ▼
┌─────────────────────────────────────┐
│  Backend (FastAPI)                  │
│  https://your-backend.railway.app   │
│                                     │
│  • Process CVs                      │
│  • ML ranking                       │
│  • SHAP explanations                │
└─────────────────────────────────────┘
```

---

## 📦 What's Included

```
railway_frontend/
├── gradio_app/                    # Gradio application
│   ├── app_with_progress.py     # Main UI
│   ├── db_manager.py             # Database & exports
│   ├── file_handler.py           # File processing
│   └── templates/                # HTML templates
├── data_storage/                 # SQLite database
├── exports/                      # Generated reports
├── requirements.txt              # Python dependencies
├── Procfile                      # Railway start command
├── runtime.txt                   # Python 3.10
├── .env.example                  # Environment template
├── .gitignore                   # Git ignore rules
└── README.md                     # This file
```

---

## ⚙️ Environment Variables Explained

### Required:
| Variable | Description | Example |
|----------|-------------|---------|
| `RANKER_API` | Backend ranking endpoint | `https://backend.railway.app/rank/enhanced` |
| `API_URL` | Backend base URL | `https://backend.railway.app` |

### Optional:
| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_FILE_SIZE_MB` | Max upload size | 10 |
| `ALLOWED_FILE_TYPES` | File types | pdf,docx,txt |
| `API_TIMEOUT` | Request timeout (sec) | 30 |

---

## 🧪 Test Your Deployment

1. **Access the UI:**
   ```
   https://your-frontend-app.up.railway.app/
   ```

2. **Upload a test CV**
3. **Enter a job description**
4. **Click "Rank Candidate"**
5. **View results with SHAP explanations**

---

## 🐛 Troubleshooting

### Issue: "Connection refused" error
**Fix:** Check `RANKER_API` points to correct backend URL

### Issue: "Backend not responding"
**Fix:** Verify backend is deployed and running

### Issue: "File upload fails"
**Fix:** Increase `MAX_FILE_SIZE_MB` in Railway variables

---

## 📊 Features

- ✅ Upload CVs (PDF, DOCX, TXT)
- ✅ Enter job descriptions
- ✅ Social media profile integration
- ✅ AI-powered ranking with SHAP
- ✅ Export results (CSV, HTML)
- ✅ Search history
- ✅ Real-time progress tracking

---

## 🔒 Security

- ✅ No sensitive data in repository
- ✅ Backend URL configurable
- ✅ File upload validation
- ✅ GDPR-compliant design

---

## 📝 Two-Service Architecture

**Why separate deployments?**

1. ✅ **Independent scaling** - Scale frontend/backend separately
2. ✅ **Better reliability** - One service failing doesn't affect the other
3. ✅ **Clearer separation** - Frontend UI / Backend API
4. ✅ **Easier debugging** - Check logs independently

---

## ✅ Deployment Checklist

- [ ] Backend deployed and URL obtained
- [ ] Frontend repository pushed to GitHub
- [ ] Railway project created for frontend
- [ ] Environment variables set (especially `RANKER_API`)
- [ ] Deployment successful
- [ ] Test upload & ranking works
- [ ] Backend connection verified

---

**Deployment Guide:** See parent folder documentation  
**Backend:** `../railway_backend/`  
**Last Updated:** December 26, 2025
