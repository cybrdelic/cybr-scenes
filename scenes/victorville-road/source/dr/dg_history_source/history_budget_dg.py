"""Read-only historical inventory reconciliation for grain representation.
The input transport ledgers are never edited or re-simulated. Erosion is charged
against historical retained class inventory first, giving a conservative proxy
for surviving deposited material, without claiming known vertical stratigraphy.
"""
import numpy as np

def reconcile(prior_deposit, later_removed, later_deposit):
 p,r,d=map(lambda v:np.asarray(v,float),(prior_deposit,later_removed,later_deposit))
 assert p.shape==r.shape==d.shape and p.shape[-1]==3
 assert np.isfinite(p).all() and np.isfinite(r).all() and np.isfinite(d).all()
 assert np.min(p)>=0 and np.min(r)>=0 and np.min(d)>=0
 debited=np.minimum(p,r);remaining=p-debited;available=remaining+d
 np.testing.assert_allclose(available+debited,p+d,rtol=2e-15,atol=1e-18)
 return {'available':available,'remaining_prior':remaining,'prior_debit':debited,'unassigned_erosion':r-debited}

def retained_cover(prior_net,later_net):
 """Same existing CI fixed-support horizon, independent of optical selection."""
 return np.maximum(np.maximum(prior_net,0)+later_net,0)
