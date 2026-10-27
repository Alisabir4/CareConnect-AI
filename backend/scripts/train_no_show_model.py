"""Train reproducible synthetic demonstration model. Never evidence of clinical accuracy."""
from pathlib import Path
import json
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_score,recall_score,f1_score,roc_auc_score,confusion_matrix
from sklearn import __version__ as sklearn_version
import joblib

rng=np.random.default_rng(42); n=4000
X=np.column_stack([rng.integers(0,45,n),rng.integers(0,7,n),rng.integers(8,18,n)])
p=1/(1+np.exp(-(-2.1+0.045*X[:,0]+0.12*(X[:,1]==0)+0.06*(X[:,2]>=15))))
y=rng.binomial(1,p)
X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
model=make_pipeline(StandardScaler(),LogisticRegression(class_weight="balanced",random_state=42,max_iter=1000)); model.fit(X_train,y_train)
prob=model.predict_proba(X_test)[:,1]; threshold=.55; pred=prob>=threshold
baseline=DummyClassifier(strategy="prior",random_state=42); baseline.fit(X_train,y_train); baseline_prob=baseline.predict_proba(X_test)[:,1]; baseline_pred=baseline_prob>=threshold
out=Path(__file__).resolve().parents[1]/"models"; out.mkdir(exist_ok=True)
joblib.dump(model,out/"no_show.joblib")
report={"available":True,"sklearn_version":sklearn_version,"dataset":"reproducible synthetic data generated in script; no real patient records","license":"synthetic; no external dataset license applies","n":n,"class_distribution":{"attended":int((y==0).sum()),"no_show":int(y.sum())},"features":["lead_days","weekday","hour"],"decision_threshold":threshold,"metrics":{"precision":precision_score(y_test,pred,zero_division=0),"recall":recall_score(y_test,pred,zero_division=0),"f1":f1_score(y_test,pred,zero_division=0),"roc_auc":roc_auc_score(y_test,prob),"confusion_matrix":confusion_matrix(y_test,pred).tolist()},"baseline":{"classifier":"DummyClassifier(strategy='prior')","precision":precision_score(y_test,baseline_pred,zero_division=0),"recall":recall_score(y_test,baseline_pred,zero_division=0),"f1":f1_score(y_test,baseline_pred,zero_division=0),"roc_auc":roc_auc_score(y_test,baseline_prob)},"limitations":"Synthetic generator measures recovery of its own assumptions only; no real-world predictive validity. Must not restrict care."}
(out/"metrics.json").write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
