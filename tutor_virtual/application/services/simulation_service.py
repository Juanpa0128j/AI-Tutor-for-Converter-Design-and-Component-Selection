
import numpy as np
from scipy.integrate import solve_ivp
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class SimulationResult:
    time: List[float]
    v_out: List[float]
    i_ind: List[float]
    metadata: Dict[str, Any]

class SimulationService:
    """Service for time-domain simulation of power converters."""
    
    def simulate_buck(self, vin: float, v_out: float, l: float, c: float, r_load: float, fsw: float, cycles: int = 100) -> SimulationResult:
        """
        Simulate Buck converter startup and steady state.
        
        Args:
            vin: Input voltage (V)
            v_out: Target output voltage (V) (used to set duty cycle)
            l: Inductance (H)
            c: Capacitance (F)
            r_load: Load resistance (Ohm)
            fsw: Switching frequency (Hz)
            cycles: Number of switching cycles to simulate
        """
        duty = v_out / vin
        period = 1.0 / fsw
        t_final = cycles * period
        
        # State variables: [i_ind, v_cap]
        def buck_ode(t, y):
            i_l, v_c = y
            
            # Switch state based on duty cycle
            # time within period
            t_rel = t % period
            is_on = t_rel < (duty * period)
            
            if is_on:
                v_sw = vin
            else:
                v_sw = 0.0 # Diode drop neglected for simplicity or add vf
                
            # Circuit equations:
            # L * di/dt = Vsw - Vout
            # C * dv/dt = Ic - Iload = Iind - Vout/R
            
            di_dt = (v_sw - v_c) / l
            dv_dt = (i_l - v_c / r_load) / c
            
            return [di_dt, dv_dt]
            
        # Initial conditions: 0A, 0V
        y0 = [0.0, 0.0]
        
        # Solve
        # Use simple RK45 or LSODA. 'radau' or 'bdf' for stiff, but buck is usually not too stiff if components are sane.
        # Max step needs to be smaller than switching period to capture switching
        max_step = period / 50.0 
        
        sol = solve_ivp(
            buck_ode, 
            [0, t_final], 
            y0, 
            max_step=max_step,
            t_eval=np.linspace(0, t_final, 1000)
        )
        
        return SimulationResult(
            time=sol.t.tolist(),
            v_out=sol.y[1].tolist(),
            i_ind=sol.y[0].tolist(),
            metadata={
                "topology": "buck",
                "vin": vin,
                "duty": duty,
                "fsw": fsw
            }
        )

    def simulate_boost(self, vin: float, v_out: float, l: float, c: float, r_load: float, fsw: float, cycles: int = 100) -> SimulationResult:
        """Simulate Boost converter."""
        if v_out <= vin:
            duty = 0.0
        else:
            duty = 1.0 - (vin / v_out)
            
        period = 1.0 / fsw
        t_final = cycles * period
        
        def boost_ode(t, y):
            i_l, v_c = y
            t_rel = t % period
            is_on = t_rel < (duty * period)
            
            # v_sw is across switch? No, let's look at equations directly.
            # L * di/dt = Vin - V_sw_node
            # If ON: V_sw_node = 0. di/dt = Vin/L. Cap is discharging: C*dv/dt = -V/R
            # If OFF: V_sw_node = Vout. di/dt = (Vin-Vout)/L. Cap charging: C*dv/dt = I_ind - V/R
            
            if is_on:
                di_dt = vin / l
                dv_dt = -(v_c / r_load) / c
            else:
                di_dt = (vin - v_c) / l
                dv_dt = (i_l - v_c / r_load) / c
                
            return [di_dt, dv_dt]
            
        y0 = [0.0, 0.0]
        max_step = period / 50.0
        
        sol = solve_ivp(
            boost_ode, [0, t_final], y0, max_step=max_step,
            t_eval=np.linspace(0, t_final, 1000)
        )
        
        return SimulationResult(
            time=sol.t.tolist(),
            v_out=sol.y[1].tolist(),
            i_ind=sol.y[0].tolist(),
            metadata={"topology": "boost", "vin": vin, "duty": duty}
        )

simulation_service = SimulationService()
