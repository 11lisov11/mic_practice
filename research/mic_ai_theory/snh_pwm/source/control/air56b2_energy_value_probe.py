"""Finite-horizon energy value of a measured query, not entropy maximization.

Reuses the complete A-B-A measurement, rollback and verification procedure.
Equal gain-hypothesis weights and cost fractions are planning priors, not a
calibrated Bayesian posterior or a guaranteed cost/energy certificate.
"""
from __future__ import annotations

import math
from collections import deque

from control.air56b2_active_probe import ActiveProbeSupervisor
from control.air56b2_probe_budget import BudgetedDynamicProbeSupervisor
from control.air56b2_dynamic_probe import DynamicProbeEvent, _finite_real


class GuardedFixedProbeSupervisor(BudgetedDynamicProbeSupervisor):
    """Strong fixed-search comparator with the same observed holding guard."""
    def __init__(self, config, budget):
        super().__init__(config,budget,budget_gate=False,payback_gate=False)
        self._holding_reference = None
        self._holding_power = None
        self._holding_window = deque()

    def _reject(self, time_s, reason, *, abort=True):
        if self.rejected and abort and not self.aborted:
            self.aborted = True
            self.reason = reason
            self._events.append(DynamicProbeEvent(time_s,self.phase,"return_fault",reason))
            if self.ever_committed:
                self.payback_status = "invalidated_by_early_return"
                self._bound_failure("hold_interrupted")
        super()._reject(time_s,reason,abort=abort)

    def step(self,time_s,measured_power_w,measured_current_peak_a,measured_voltage_peak_v,
             measured_speed_rad_s,reference_speed_rad_s,voltage_limit_v=None):
        time_s = _finite_real("time_s",time_s)
        if time_s < 0 or (self._last_time_s is not None and time_s <= self._last_time_s):
            raise ValueError("nonnegative increasing time required")
        try:
            power,current,voltage,speed,reference = [_finite_real("observation",v) for v in
                (measured_power_w,measured_current_peak_a,measured_voltage_peak_v,
                 measured_speed_rad_s,reference_speed_rad_s)]
            cap = self._voltage_cap_v
            if voltage_limit_v is not None:
                limit = _finite_real("voltage cap",voltage_limit_v)
                if limit <= 0:
                    raise ValueError("positive voltage cap required")
                cap = min(cap,limit)
            if current < 0 or voltage < 0:
                raise ValueError("nonnegative peaks required")
        except ValueError:
            self._reject(time_s,"invalid_measurement")
        else:
            if current > self.config.current_limit_a:
                self._reject(time_s,"current_limit")
            elif voltage > cap:
                self._reject(time_s,"voltage_limit")
            elif (self._last_time_s is not None and
                  time_s-self._last_time_s > self.config.dt_s*(1+1e-9) and
                  self.phase not in ("waiting","rollback","rejected")):
                self._reject(time_s,"sample_gap")
            elif self.phase == "committed":
                self._holding_window.append((time_s,power))
                while time_s-self._holding_window[0][0] > self.config.window_s:
                    self._holding_window.popleft()
                mean = math.fsum(p for _,p in self._holding_window)/len(self._holding_window)
                if (abs(reference-self._holding_reference) > 1e-9 or
                    abs(speed-reference) > self.config.speed_error_limit_rad_s or
                    abs(mean-self._holding_power) > self.config.repeat_drift_limit_w):
                    self._reject(time_s,"observed_regime_change")
        before = self.phase
        result = super().step(time_s,measured_power_w,measured_current_peak_a,
                             measured_voltage_peak_v,measured_speed_rad_s,reference_speed_rad_s,
                             voltage_limit_v)
        if before != "committed" and self.phase == "committed":
            self._holding_reference = reference_speed_rad_s
            self._holding_power = self.measurements["candidateverify"].power_w
        return result


def candidate_value(gain_w, hold_s, deployment_cost_j, spent_j, budget_j, margin_w):
    """Future value of an admissible deployment; past costs must be repayable."""
    if not all(math.isfinite(x) for x in (gain_w,hold_s,deployment_cost_j,spent_j,budget_j,margin_w)):
        raise ValueError("finite inputs required")
    if min(deployment_cost_j,spent_j,budget_j,margin_w) < 0:
        raise ValueError("nonnegative costs, budget and margin required")
    future = gain_w*hold_s-deployment_cost_j
    if (hold_s <= 0 or gain_w < margin_w or spent_j+deployment_cost_j > budget_j
            or future <= spent_j):
        return 0.
    return future


class EnergyValueProbeSupervisor(ActiveProbeSupervisor):
    """Choose accept / query / stop by one-step expected future energy value.

    A query only enables its OWN measured candidate, not an unmeasured optimum.
    Exploration time, full query cost, verification and final return reduce
    its value. The baseline action is worth zero *from now*: sunk costs are
    retained for payback but do not make further loss preferable to stopping.
    ``greedy`` is the strong first-good low/high paired baseline.
    """
    def __init__(self, config, active, *, greedy=False, learned_cost=True,
                 query_order=(0,1,2,3), greedy_full_menu=False):
        super().__init__(config, active, learned_cost=learned_cost)
        if not isinstance(greedy, bool):
            raise TypeError("greedy must be boolean")
        self.greedy = greedy
        if not isinstance(greedy_full_menu,bool):
            raise TypeError("greedy_full_menu must be boolean")
        self.greedy_full_menu = greedy_full_menu
        if sorted(query_order) != list(range(len(self.ids))):
            raise ValueError("query_order must be a permutation of candidate indices")
        self.query_order = tuple(query_order)
        self.cost_fractions = (.25, .5, 1.)

    def _hold_s(self, index, time_s):
        return (self.active.hold_until_s-time_s-self.stage_s(self.ids[index])
                - self.return_s(self.ids[index]))

    def forecast_after_query(self, index, query_index, observed_cost):
        """The same empirical full forecast after a hypothetical completed query."""
        if not self.learned_cost:
            return self.cycle_cost(self.ids[index])
        amplitude = abs(self.ids[index]-self.config.baseline_id_a)
        records = self.cycles + [dict(excess_j=observed_cost,
            amplitude_a=abs(self.ids[query_index]-self.config.baseline_id_a))]
        return self.active.cost_floor_j + self.active.cost_multiplier*max(
            c["excess_j"]*max(1.,(amplitude/max(c["amplitude_a"],1e-12))**2) for c in records)

    def _value(self, index, gain, time_s, spent, deployment_cost_j=None):
        value = candidate_value(gain, self._hold_s(index,time_s),
            self.cycle_cost(self.ids[index]) if deployment_cost_j is None else deployment_cost_j, spent,
            self.active.max_estimated_cost_j, self.config.improvement_margin_w)
        return value if value-spent > self.active.minimum_net_gain_j else 0.

    def expected_query_value(self, index, time_s, measured):
        duration = self.stage_s(self.ids[index])+self.return_s(self.ids[index])
        if self._hold_s(index,time_s+duration) <= 0:
            return None
        admission_cost = self.cycle_cost(self.ids[index])
        if self.spent_estimate_j+admission_cost > self.active.max_estimated_cost_j:
            return None
        # Width is propagated from past observed windows, never tuned using
        # the unknown outcome. No posterior confidence interpretation is made.
        width = max([self.active.gain_error_floor_w] + [c["error_width_w"] for c in self.cycles])
        # One action per observable outcome bin, not one per hidden hypothesis.
        # Query cost is observed after the completed cycle in this surrogate.
        branches = {}
        for h in self.hypotheses:
            for fraction in self.cost_fractions:
                key = (math.floor(h[index]/(2*width)),fraction)
                branches.setdefault(key,[]).append(h[index])
        weighted = []
        for (bucket,fraction),gains in branches.items():
            cost = admission_cost*fraction
            spent = self.spent_estimate_j+cost
            observed_gain = (bucket+.5)*2*width
            values = [0., self._value(index,observed_gain-width,time_s+duration,spent,
                                      self.forecast_after_query(index,index,cost))]
            values += [self._value(j,c["gain_lower_heuristic_w"],time_s+duration,spent,
                                   self.forecast_after_query(j,index,cost))
                       for j,c in measured.items()]
            weighted.append(len(gains)*(max(values)-cost))
        return math.fsum(weighted)/(len(self.hypotheses)*len(self.cost_fractions))

    def _decide(self, time_s):
        measured = {c["index"]:c for c in self.cycles}
        immediate = [(self._value(i,c["gain_lower_heuristic_w"],time_s,self.spent_estimate_j),i)
                     for i,c in measured.items()]
        best_value,best_index = max(immediate,default=(0.,-1))
        choices = []
        if len(self.cycles) < self.active.max_probes:
            order = self.query_order[:2] if self.greedy and not self.greedy_full_menu else self.query_order
            for i in order:
                if i in measured:
                    continue
                expected = self.expected_query_value(i,time_s,measured)
                choices.append(dict(index=i,id_a=self.ids[i],expected_future_value_j=expected,
                                    admission_cost_j=self.cycle_cost(self.ids[i])))
        feasible = [c for c in choices if c["expected_future_value_j"] is not None]
        chosen = (feasible[0] if self.greedy and feasible else
                  max(feasible,key=lambda c:(c["expected_future_value_j"],-c["index"]),default=None))
        continue_value = chosen["expected_future_value_j"] if chosen else 0.
        event = dict(time_s=time_s,survivors=len(self.hypotheses),choices=choices,
                     immediate_future_value_j=best_value,continue_future_value_j=continue_value)
        self.decisions.append(event)
        if best_value > 0 and (self.greedy or best_value >= continue_value):
            self.candidate_id_a = self.ids[best_index]
            self.projected_net_j = best_value-self.spent_estimate_j
            event["action"] = "verify_measured_candidate"
            self._start_episode(time_s,"verification_hold_return",self.cycle_cost(self.candidate_id_a))
            self._enter_stage("candidateverify",time_s)
        elif chosen and (self.greedy or continue_value > 0):
            self._query = chosen["index"]
            self._query_started = time_s
            self._cycle_cost_prediction = chosen["admission_cost_j"]
            self._return_prediction_s = self.return_s(chosen["id_a"])
            self._intervals = []
            event.update(action="query",selected_index=self._query)
            self._start_episode(time_s,"query_return",self._cycle_cost_prediction)
            self._enter_stage("query",time_s)
        else:
            event["action"] = "stop"
            self._reject(time_s,"no_positive_future_value",abort=False)

    def summary(self):
        return dict(super().summary(),criterion="greedy_first_good" if self.greedy else "one_step_energy_value",
                    query_order=self.query_order,
                    greedy_full_menu=self.greedy_full_menu,
                    planning_cost_fractions=self.cost_fractions,
                    planning_prior="equal_gain_hypotheses_and_cost_fractions_not_calibrated")
