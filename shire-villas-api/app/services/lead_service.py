import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.lead import Lead, Activity, LeadTemperature, LeadStatus

BUDGET_KEYWORDS={"20+":100,"20 cr":100,"above 20":100,"15-20":90,"15 to 20":90,"10-15":80,"10 to 15":80,"5-10":40,"5 to 10":40,"below 5":15,"under 5":15,"not sure":20,"unsure":20}
TIMELINE_KEYWORDS={"immediately":100,"0-3":100,"this month":100,"3-6":75,"3 to 6":75,"6-12":50,"6 to 12":50,"1 year+":25,"just exploring":15,"browsing":15}
AUTHORITY_KEYWORDS={"sole decision":100,"myself":100,"i decide":100,"joint":65,"with spouse":65,"with family":65,"influencer":30,"researching for someone":20}
NEED_KEYWORDS={"second home":80,"investment":85,"relocation":90,"vacation home":75,"rental income":70,"just curious":20}

def _match_score(answer, table, default=40):
    a=(answer or '').lower()
    for key,score in table.items():
        if key in a: return score
    return default

def score_from_answers(answers):
    budget=_match_score(answers.get('budget',''),BUDGET_KEYWORDS)
    timeline=_match_score(answers.get('timeline',''),TIMELINE_KEYWORDS)
    authority=_match_score(answers.get('authority',''),AUTHORITY_KEYWORDS)
    need=_match_score(answers.get('need',''),NEED_KEYWORDS)
    fit_raw=answers.get('fit','').lower()
    fit=85 if any(k in fit_raw for k in ['goa','siolim','4bhk','villa']) else 50
    overall=round(budget*.30+timeline*.20+authority*.20+need*.15+fit*.15,1)
    temperature=LeadTemperature.HOT if overall>=75 else LeadTemperature.WARM if overall>=50 else LeadTemperature.COLD if overall>=25 else LeadTemperature.UNQUALIFIED
    return {'budget_score':budget,'authority_score':authority,'need_score':need,'timeline_score':timeline,'fit_score':fit,'overall_score':overall,'temperature':temperature}

def recommended_action(t):
    return {LeadTemperature.HOT:'Call within 15 minutes. Offer a private site visit this week.',LeadTemperature.WARM:'Call within 24 hours. Send brochure + virtual tour link.',LeadTemperature.COLD:'Add to nurture sequence. Re-engage in 2 weeks.',LeadTemperature.UNQUALIFIED:'Low priority. Send general information only.'}[t]

def log_activity(db:Session,lead_id,action_type,description='',meta=None):
    a=Activity(lead_id=lead_id,action_type=action_type,description=description,meta=json.dumps(meta) if meta else None)
    db.add(a); db.commit(); db.refresh(a); return a

def get_dashboard_stats(db:Session):
    total=db.query(Lead).count(); hot=db.query(Lead).filter(Lead.temperature==LeadTemperature.HOT).count(); warm=db.query(Lead).filter(Lead.temperature==LeadTemperature.WARM).count(); cold=db.query(Lead).filter(Lead.temperature==LeadTemperature.COLD).count(); converted=db.query(Lead).filter(Lead.status==LeadStatus.CONVERTED).count()
    avg=db.query(func.avg(Lead.budget_score),func.avg(Lead.authority_score),func.avg(Lead.need_score),func.avg(Lead.timeline_score),func.avg(Lead.fit_score)).first()
    recent=db.query(Activity).order_by(Activity.created_at.desc()).limit(20).all(); since=datetime.now(timezone.utc)-timedelta(days=7)
    return {'total_leads':total,'hot':hot,'warm':warm,'cold':cold,'converted':converted,'conversion_rate':round((converted/total)*100,1) if total else 0.0,'leads_last_7_days':db.query(Lead).filter(Lead.created_at>=since).count(),'avg_bant':{'budget':round(avg[0] or 0,1),'authority':round(avg[1] or 0,1),'need':round(avg[2] or 0,1),'timeline':round(avg[3] or 0,1),'fit':round(avg[4] or 0,1)},'funnel':{'new':db.query(Lead).filter(Lead.status==LeadStatus.NEW).count(),'in_progress':db.query(Lead).filter(Lead.status==LeadStatus.IN_PROGRESS).count(),'qualified':db.query(Lead).filter(Lead.status==LeadStatus.QUALIFIED).count(),'site_visit':db.query(Lead).filter(Lead.status==LeadStatus.SITE_VISIT_SCHEDULED).count(),'converted':converted},'recent_activities':[{'id':a.id,'lead_id':a.lead_id,'action_type':a.action_type,'description':a.description,'created_at':a.created_at.isoformat()} for a in recent]}
