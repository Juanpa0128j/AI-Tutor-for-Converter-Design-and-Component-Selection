"""Mouser Search API adapter."""

from __future__ import annotations

import os
import logging
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from tutor_virtual.domain.components import (
    Component, ComponentRequirements, ComponentType,
    MOSFET, Diode, Capacitor, Inductor
)
from tutor_virtual.domain.ports import ComponentCatalogPort

from .base import BaseCatalogAdapter

logger = logging.getLogger(__name__)


class MouserAdapter(BaseCatalogAdapter, ComponentCatalogPort):
    """Adapter for Mouser Search API v1."""
    
    # API Endpoints
    BASE_URL = "https://api.mouser.com/api/v1"
    SEARCH_KEYWORD_URL = f"{BASE_URL}/search/keyword"
    SEARCH_PARTNUMBER_URL = f"{BASE_URL}/search/partnumber"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_requests: int = 100,
        rate_limit_period: int = 60
    ):
        """
        Initialize Mouser adapter.
        
        Args:
            api_key: Mouser API key (Search API)
            rate_limit_requests: Max requests per period
            rate_limit_period: Period in seconds for rate limiting
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for Mouser API. Install with: pip install httpx"
            )

        load_dotenv()
        api_key = api_key or os.getenv("MOUSER_API_KEY")
        super().__init__(
            api_key=api_key,
            rate_limit_requests=rate_limit_requests,
            rate_limit_period=rate_limit_period
        )
        
        if not self.api_key:
            raise ValueError("Mouser API key not provided")
        
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    def _build_search_keyword(self, requirements: ComponentRequirements) -> str:
        """Build search keyword from component requirements.
        
        Uses a simplified approach focusing on component type and critical specs.
        Mouser's search is quite flexible and will return results even with partial matches.
        """
        keywords = []
        
        # Component type mapping - use generic terms for better results
        type_map = {
            ComponentType.MOSFET: "MOSFET",
            ComponentType.DIODE: "Rectifier Diode",  # More specific for power applications
            ComponentType.CAPACITOR: "Electrolytic Capacitor",  # More specific for power supplies
            ComponentType.INDUCTOR: "Power Inductor",  # More specific for power applications
            ComponentType.TRANSFORMER: "Transformer",
            ComponentType.RESISTOR: "Resistor"
        }
        keywords.append(type_map.get(requirements.component_type, ""))
        
        # For capacitors, prioritize capacitance value over voltage
        if requirements.component_type == ComponentType.CAPACITOR and requirements.capacitance_min:
            cap_uf = requirements.capacitance_min * 1e6  # Convert to µF
            if cap_uf >= 1000:
                cap_mf = cap_uf / 1000
                keywords.append(f"{cap_mf:.0f}mF")
            elif cap_uf >= 1:
                keywords.append(f"{cap_uf:.0f}uF")
            else:
                cap_nf = requirements.capacitance_min * 1e9
                keywords.append(f"{cap_nf:.0f}nF")
        
        # For inductors, prioritize inductance value
        elif requirements.component_type == ComponentType.INDUCTOR and requirements.inductance_min:
            ind_uh = requirements.inductance_min * 1e6  # Convert to µH
            if ind_uh >= 1000:
                ind_mh = requirements.inductance_min * 1e3
                keywords.append(f"{ind_mh:.1f}mH")
            else:
                # Round to common inductor values for better search results
                common_inductances = [1, 2.2, 3.3, 4.7, 10, 22, 33, 47, 100, 150, 220, 330, 470, 1000]
                for ind_val in common_inductances:
                    if ind_uh <= ind_val:
                        keywords.append(f"{ind_val}uH")
                        break
                else:
                    # If larger than all common values, use closest match
                    keywords.append(f"{int(ind_uh)}uH")
        
        # For semiconductors (MOSFETs, Diodes), add voltage if significant
        elif requirements.component_type in [ComponentType.MOSFET, ComponentType.DIODE]:
            if requirements.voltage_max and requirements.voltage_max > 10:
                voltage_v = requirements.voltage_max * requirements.voltage_margin
                # Round up to common voltage ratings
                common_voltages = [20, 30, 40, 50, 60, 75, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 1700]
                for v in common_voltages:
                    if voltage_v <= v:
                        keywords.append(f"{v}V")
                        break
        
        return " ".join(keywords)
    
    async def search_components(
        self,
        requirements: ComponentRequirements,
        limit: int = 100
    ) -> List[Component]:
        """
        Search Mouser catalog using keyword search.
        
        Mouser API uses simple keyword search with API key authentication.
        """
        await self._make_request()  # Rate limiting
        
        keyword = self._build_search_keyword(requirements)
        
        client = await self._get_http_client()
        
        # Build request payload
        payload = {
            "SearchByKeywordRequest": {
                "keyword": keyword,
                "records": min(limit, 50),  # Mouser max 50 per request
                "startingRecord": 0,
                "searchOptions": "InStock",  # Only in-stock items
                "searchWithYourSignUpLanguage": "en"
            }
        }
        
        # Make request
        response = await client.post(
            f"{self.SEARCH_KEYWORD_URL}?apiKey={self.api_key}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Parse response
        components = []
        search_results = data.get("SearchResults", {})
        parts = search_results.get("Parts", [])
        
        logger.debug(f"🔍 Mouser API returned {len(parts)} parts")
        
        for i, part in enumerate(parts, 1):
            try:
                logger.debug(f"   Parsing part {i}/{len(parts)}...")
                component = self._parse_part(part)
                if component:
                    components.append(component)
                    logger.debug(f"   ✅ Created {type(component).__name__}: {component.part_number}")
                else:
                    logger.warning(f"   ⚠️  _parse_part returned None")
            except Exception as e:
                logger.error(f"   ❌ Error parsing part {i}: {type(e).__name__}: {e}", exc_info=True)
        
        return components
    
    async def get_component_details(self, part_number: str) -> Optional[Component]:
        """Get detailed specifications for a specific part number."""
        await self._make_request()  # Rate limiting
        
        client = await self._get_http_client()
        
        # Build request payload
        payload = {
            "SearchByPartRequest": {
                "mouserPartNumber": part_number,
                "partSearchOptions": "Exact"
            }
        }
        
        response = await client.post(
            f"{self.SEARCH_PARTNUMBER_URL}?apiKey={self.api_key}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Parse response
        search_results = data.get("SearchResults", {})
        parts = search_results.get("Parts", [])
        
        if parts:
            return self._parse_part(parts[0])
        
        return None
    
    def _parse_part(self, part: Dict[str, Any]) -> Optional[Component]:
        """Parse Mouser part JSON to domain Component model."""
        try:
            # Extract common fields
            part_number = part.get("ManufacturerPartNumber", "")
            manufacturer = part.get("Manufacturer", "Unknown")
            description = part.get("Description", "")
            
            logger.debug(f"      Part: {manufacturer} {part_number}")
            logger.debug(f"      Description: {description}")
            
            # Pricing (get quantity 1 price)
            price_breaks = part.get("PriceBreaks", [])
            price_usd = 0.0
            if price_breaks:
                # Parse price string like "$1.23" or "1.23 USD"
                price_str = price_breaks[0].get("Price", "0")
                price_usd = self._parse_price(price_str)
            
            # Availability
            availability = int(part.get("AvailabilityInStock", 0))
            
            # URLs
            datasheet_url = part.get("DataSheetUrl")
            product_url = part.get("ProductDetailUrl")  # Direct link to Mouser product page
            
            # Category to determine component type
            category = part.get("Category", "").lower()
            
            # DEBUG: Log category to see what we're getting
            logger.debug(f"🔍 Parsing part {part_number}: category='{category}'")
            
            # Product attributes (specifications)
            attributes = {}
            for attr in part.get("ProductAttributes", []):
                attr_name = attr.get("AttributeName", "")
                attr_value = attr.get("AttributeValue", "")
                attributes[attr_name] = attr_value
            
            logger.debug(f"      Attributes found: {list(attributes.keys())}")
            
            # Determine component type and create model (support Spanish and English)
            if "mosfet" in category or "fet" in category:
                return self._create_mosfet(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    product_url, attributes
                )
            elif "diode" in category or "diodo" in category or "rectifier" in category or "rectificador" in category:
                return self._create_diode(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    product_url, attributes
                )
            elif "capacitor" in category or "capacitores" in category:
                return self._create_capacitor(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    product_url, attributes
                )
            elif "inductor" in category or "inductores" in category or "choke" in category or "bobina" in category:
                return self._create_inductor(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    product_url, attributes
                )
            else:
                # Generic component
                return Component(
                    part_number=part_number,
                    manufacturer=manufacturer,
                    description=description,
                    catalog="mouser",
                    price_usd=price_usd,
                    availability=availability,
                    datasheet_url=datasheet_url,
                    product_url=product_url
                )
        
        except Exception as e:
            logger.warning(f"Error parsing Mouser part: {e}")
            return None
    
    def _create_mosfet(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        product_url: Optional[str], attrs: Dict[str, str]
    ) -> MOSFET:
        """Create MOSFET from Mouser attributes or description."""
        # Try to get from attributes first
        vds_max = self._parse_voltage(attrs.get("Drain to Source Voltage (Vdss)", "0V"))
        id_continuous = self._parse_current(attrs.get("Continuous Drain Current (Id)", "0A"))
        rds_on = self._parse_resistance(attrs.get("On State Resistance (Rds(on))", "0"))
        
        # If critical attributes are empty, try parsing from description
        if vds_max == 0.0 or id_continuous == 0.0:
            vds_desc, id_desc = self._extract_mosfet_specs_from_description(description)
            if vds_max == 0.0:
                vds_max = vds_desc
            if id_continuous == 0.0:
                id_continuous = id_desc
        
        logger.debug(f"         MOSFET specs: VDS={vds_max}V, ID={id_continuous}A, RDS(on)={rds_on}Ω")
        
        return MOSFET(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="mouser",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            product_url=product_url,
            type=attrs.get("Transistor Polarity", "N-Channel"),
            vds_max=vds_max,
            id_continuous=id_continuous,
            id_pulsed=self._parse_current(attrs.get("Pulsed Drain Current (Idm)", "0A")),
            rds_on=rds_on,
            vgs_threshold=self._parse_voltage(attrs.get("Gate Threshold Voltage (Vgs(th))", "0V")),
            qg_total=self._parse_charge(attrs.get("Gate Charge (Qg)", "0nC")),
            package=attrs.get("Packaging", "Unknown")
        )
    
    def _create_diode(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        product_url: Optional[str], attrs: Dict[str, str]
    ) -> Diode:
        """Create Diode from Mouser attributes or description."""
        # Try to get from attributes first
        vrrm = self._parse_voltage(attrs.get("Peak Reverse Voltage (Max)", "0V"))
        if_avg = self._parse_current(attrs.get("Average Forward Current (If)", "0A"))
        
        # If attributes are empty, try parsing from part number or description
        # Part numbers like FSV10150V or SDT15150VP5-7 contain voltage ratings
        if vrrm == 0.0:
            vrrm = self._extract_diode_voltage_from_part_number(part_number)
        
        return Diode(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="mouser",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            product_url=product_url,
            type=attrs.get("Diode Type", "Schottky"),
            vrrm=vrrm,
            if_avg=if_avg if if_avg > 0 else 1.0,  # Default 1A if not specified
            vf=self._parse_voltage(attrs.get("Forward Voltage (Vf)", "0V")),
            trr=self._parse_time(attrs.get("Reverse Recovery Time (trr)", "")),
            package=attrs.get("Packaging", "Unknown")
        )
    
    def _create_capacitor(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        product_url: Optional[str], attrs: Dict[str, str]
    ) -> Capacitor:
        """Create Capacitor from Mouser attributes or description."""
        # Try to get from attributes first
        capacitance = self._parse_capacitance(attrs.get("Capacitance", "0F"))
        voltage_rating = self._parse_voltage(attrs.get("Voltage Rating", "0V"))
        
        # If attributes are empty, try parsing from description
        if capacitance == 0.0 or voltage_rating == 0.0:
            cap_from_desc, volt_from_desc = self._extract_capacitor_specs_from_description(description)
            if capacitance == 0.0:
                capacitance = cap_from_desc
            if voltage_rating == 0.0:
                voltage_rating = volt_from_desc
        
        logger.debug(f"         Capacitor specs: C={capacitance*1e6:.2f}µF, V={voltage_rating}V")
        
        return Capacitor(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="mouser",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            product_url=product_url,
            capacitance=capacitance,
            voltage_rating=voltage_rating,
            tolerance=self._parse_tolerance(attrs.get("Tolerance", "0%")),
            dielectric=attrs.get("Dielectric Characteristic", "Unknown"),
            esr=self._parse_resistance(attrs.get("ESR", "")),
            ripple_current=self._parse_current(attrs.get("Ripple Current", "")),
            package=attrs.get("Packaging", "Unknown")
        )
    
    def _create_inductor(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        product_url: Optional[str], attrs: Dict[str, str]
    ) -> Inductor:
        """Create Inductor from Mouser attributes or description."""
        # Try to get from attributes first
        inductance = self._parse_inductance(attrs.get("Inductance", "0H"))
        current_rating = self._parse_current(attrs.get("Current Rating", "0A"))
        
        # If attributes are empty, try parsing from description
        if inductance == 0.0 or current_rating == 0.0:
            ind_from_desc, curr_from_desc = self._extract_inductor_specs_from_description(description)
            if inductance == 0.0:
                inductance = ind_from_desc
            if current_rating == 0.0:
                current_rating = curr_from_desc
        
        logger.debug(f"         Inductor specs: L={inductance*1e6:.2f}µH, I={current_rating}A")
        
        return Inductor(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="mouser",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            product_url=product_url,
            inductance=inductance,
            current_rating=current_rating,
            dcr=self._parse_resistance(attrs.get("DC Resistance (DCR)", "0")) or 0.0,
            saturation_current=self._parse_current(attrs.get("Saturation Current", "0A")),
            package=attrs.get("Packaging", "Unknown"),
            core_material=attrs.get("Core Material", None)
        )
    
    # Unit parsing helpers
    def _extract_mosfet_specs_from_description(self, description: str) -> tuple[float, float]:
        """Extract VDS and ID from MOSFET description text.
        
        Examples:
        - "N-Channel 100V 30A" -> (100.0, 30.0)
        - "MOSFET 600V 10A" -> (600.0, 10.0)
        """
        import re
        
        vds = 0.0
        id_cont = 0.0
        
        # Extract voltage (look for patterns like 100V, 600V)
        volt_match = re.search(r'(\d+(?:\.\d+)?)\s*V(?!o)', description)  # (?!o) to avoid "Voltage"
        if volt_match:
            vds = float(volt_match.group(1))
        
        # Extract current (look for patterns like 30A, 10A)
        curr_match = re.search(r'(\d+(?:\.\d+)?)\s*A(?!l)', description)  # (?!l) to avoid "Aluminum"
        if curr_match:
            id_cont = float(curr_match.group(1))
        
        return vds, id_cont
    
    def _extract_inductor_specs_from_description(self, description: str) -> tuple[float, float]:
        """Extract inductance and current rating from description text.
        
        Examples:
        - "100uH 5A" -> (0.0001, 5.0)
        - "100  UH  20%" -> (0.0001, 0.0)
        - "47uH 3.2A" -> (0.000047, 3.2)
        - "100uH UnShld 10% 5.6A" -> (0.0001, 5.6)
        """
        import re
        
        inductance = 0.0
        current = 0.0
        
        # Extract inductance (look for patterns like 100uH, 100  UH, 47uH)
        # Allow multiple spaces between number and unit
        ind_match = re.search(r'(\d+(?:\.\d+)?)\s*u?H', description, re.IGNORECASE)
        if ind_match:
            ind_value = float(ind_match.group(1))
            # Convert µH to H
            inductance = ind_value * 1e-6
        
        # Extract current (look for patterns like 5A, 3.2A, 5.6A)
        # Search after inductance value to avoid confusion
        curr_match = re.search(r'(\d+(?:\.\d+)?)-?\s*A(?!l)', description, re.IGNORECASE)  # (?!l) to avoid matching "Aluminum"
        if curr_match:
            current = float(curr_match.group(1))
        
        return inductance, current
    
    def _extract_diode_voltage_from_part_number(self, part_number: str) -> float:
        """Extract voltage rating from diode part number.
        
        Examples:
        - FSV10150V -> 150V
        - SDT15150VP5-7 -> 150V
        """
        import re
        
        # Look for pattern like 150V in part number
        match = re.search(r'(\d+)V', part_number)
        if match:
            return float(match.group(1))
        
        return 0.0
    
    def _extract_capacitor_specs_from_description(self, description: str) -> tuple[float, float]:
        """Extract capacitance and voltage from description text.
        
        Examples:
        - "63V 91000uF 20%" -> (0.091, 63.0)
        - "63volts 47000uF 20%" -> (0.047, 63.0)
        - "100uF 63V 20%" -> (0.0001, 63.0)
        """
        import re
        
        capacitance = 0.0
        voltage = 0.0
        
        # Extract capacitance (look for patterns like 91000uF, 47000uF, 100uF)
        cap_match = re.search(r'(\d+(?:\.\d+)?)\s*u?F', description, re.IGNORECASE)
        if cap_match:
            cap_value = float(cap_match.group(1))
            # Convert µF to F
            capacitance = cap_value * 1e-6
        
        # Extract voltage (look for patterns like 63V, 63volts, 100VDC)
        volt_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:V|volts?|VDC)', description, re.IGNORECASE)
        if volt_match:
            voltage = float(volt_match.group(1))
        
        return capacitance, voltage
    
    def _parse_price(self, value: str) -> float:
        """Parse price string (e.g., '$1.23' or '1.23 USD')."""
        try:
            # Remove currency symbols and text
            value = value.replace("$", "").replace("USD", "").replace("EUR", "").strip()
            return float(value)
        except:
            return 0.0
    
    def _parse_voltage(self, value: str) -> float:
        """Parse voltage string to float (e.g., '100V' -> 100.0)."""
        try:
            value = value.replace("V", "").strip()
            if "k" in value.lower():
                return float(value.replace("k", "").replace("K", "")) * 1000.0
            return float(value)
        except:
            return 0.0
    
    def _parse_current(self, value: str) -> float:
        """Parse current string to float (e.g., '10A' -> 10.0)."""
        try:
            value = value.replace("A", "").strip()
            if not value or value == "-":
                return 0.0
            if "m" in value:  # milliamps
                return float(value.replace("m", "")) / 1000.0
            if "µ" in value or "u" in value:  # microamps
                return float(value.replace("µ", "").replace("u", "")) / 1e6
            return float(value)
        except:
            return 0.0
    
    def _parse_resistance(self, value: str) -> Optional[float]:
        """Parse resistance string to float (e.g., '0.044Ω' -> 0.044)."""
        try:
            value = value.replace("Ω", "").replace("Ohm", "").replace("ohm", "").strip()
            if not value or value == "-":
                return None
            if "m" in value.lower():  # milliohms
                return float(value.replace("m", "").replace("M", "")) / 1000.0
            if "k" in value.lower():  # kilohms
                return float(value.replace("k", "").replace("K", "")) * 1000.0
            return float(value)
        except:
            return None
    
    def _parse_capacitance(self, value: str) -> float:
        """Parse capacitance string to float in Farads."""
        try:
            value = value.replace("F", "").strip()
            if "µ" in value or "u" in value:  # microfarads
                return float(value.replace("µ", "").replace("u", "")) * 1e-6
            elif "n" in value:  # nanofarads
                return float(value.replace("n", "")) * 1e-9
            elif "p" in value:  # picofarads
                return float(value.replace("p", "")) * 1e-12
            return float(value)
        except:
            return 0.0
    
    def _parse_inductance(self, value: str) -> float:
        """Parse inductance string to float in Henries."""
        try:
            value = value.replace("H", "").strip()
            if "µ" in value or "u" in value:  # microhenries
                return float(value.replace("µ", "").replace("u", "")) * 1e-6
            elif "m" in value:  # millihenries
                return float(value.replace("m", "")) * 1e-3
            elif "n" in value:  # nanohenries
                return float(value.replace("n", "")) * 1e-9
            return float(value)
        except:
            return 0.0
    
    def _parse_tolerance(self, value: str) -> float:
        """Parse tolerance string to float (e.g., '±20%' -> 20.0)."""
        try:
            return float(value.replace("%", "").replace("±", "").replace("+/-", "").strip())
        except:
            return 0.0
    
    def _parse_charge(self, value: str) -> float:
        """Parse charge string to float in nC."""
        try:
            value = value.replace("nC", "").replace("nc", "").strip()
            return float(value)
        except:
            return 0.0
    
    def _parse_time(self, value: str) -> Optional[float]:
        """Parse time string to float in nanoseconds."""
        try:
            value = value.replace("ns", "").strip()
            if not value or value == "-":
                return None
            if "µ" in value or "u" in value:  # microseconds
                return float(value.replace("µ", "").replace("u", "")) * 1000.0
            return float(value)
        except:
            return None
    
    def get_catalog_name(self) -> str:
        """Return catalog name."""
        return "mouser"
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
