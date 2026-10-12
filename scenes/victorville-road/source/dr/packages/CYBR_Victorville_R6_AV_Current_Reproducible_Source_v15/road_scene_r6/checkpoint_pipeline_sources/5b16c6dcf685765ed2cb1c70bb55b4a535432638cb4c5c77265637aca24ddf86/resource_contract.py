"""Validate sampled and kernel-recorded peaks, including between-poll bursts."""
import math
def resource_violations(receipt,cap_mib):
 reasons=[]
 if receipt.get('RSS_cap_MiB')!=cap_mib:reasons.append('Recorded resource cap differs from requested cap')
 for key in ('peak_process_tree_RSS_MiB','kernel_max_child_RSS_MiB'):
  value=receipt.get(key)
  if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:reasons.append('Missing or invalid resource peak: '+key)
  elif value>cap_mib:reasons.append(key+' exceeded requested RSS cap')
 if receipt.get('exit_code')!=0:reasons.append('Capture process or guard did not succeed')
 return reasons
