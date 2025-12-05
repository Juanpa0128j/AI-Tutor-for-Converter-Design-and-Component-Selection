"""DigiKey API v4 adapter with OAuth2 authentication."""

from __future__ import annotations

import os
from typing import List, Optional, Dict, Any
import asyncio
import time

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


class DigiKeyAdapter(BaseCatalogAdapter, ComponentCatalogPort):
    """Adapter for DigiKey API v4 with OAuth2 2-legged flow."""
    
    # API Endpoints
    SANDBOX_TOKEN_URL = "https://sandbox-api.digikey.com/v1/oauth2/token"
    SANDBOX_SEARCH_URL = "https://sandbox-api.digikey.com/products/v4/search"
    SANDBOX_DETAILS_URL = "https://sandbox-api.digikey.com/products/v4/search/{part_number}/productdetails"
    
    PRODUCTION_TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
    PRODUCTION_SEARCH_URL = "https://api.digikey.com/products/v4/search"
    PRODUCTION_DETAILS_URL = "https://api.digikey.com/products/v4/search/{part_number}/productdetails"
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        rate_limit_requests: int = 100,
        rate_limit_period: int = 60,
        use_sandbox: bool = False
    ):
        """
        Initialize DigiKey adapter.
        
        Args:
            client_id: DigiKey OAuth2 client ID
            client_secret: DigiKey OAuth2 client secret
            rate_limit_requests: Max requests per period
            rate_limit_period: Period in seconds for rate limiting
            use_sandbox: Use sandbox environment instead of production
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for DigiKey API. Install with: pip install httpx"
            )
        
        self.client_id = client_id or os.getenv("DIGIKEY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("DIGIKEY_CLIENT_SECRET")
        self.use_sandbox = use_sandbox or os.getenv("DIGIKEY_USE_SANDBOX", "false").lower() == "true"
        
        super().__init__(
            api_key=self.client_id,
            rate_limit_requests=rate_limit_requests,
            rate_limit_period=rate_limit_period
        )
        
        if not self.client_id or not self.client_secret:
            raise ValueError("DigiKey API credentials not provided")
        
        # OAuth2 token management
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def _get_access_token(self) -> str:
        """
        Get OAuth2 access token.
        
        For Production: Uses 2-legged flow (client credentials)
        For Sandbox: Uses stored refresh token or raises error if not available
        
        Caches token until expiration.
        """
        # Check if we have a valid cached token
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        # Request new token
        token_url = self.SANDBOX_TOKEN_URL if self.use_sandbox else self.PRODUCTION_TOKEN_URL
        
        client = await self._get_http_client()
        
        # Check if we have a refresh token for sandbox
        refresh_token = os.getenv("DIGIKEY_REFRESH_TOKEN")
        
        if self.use_sandbox and refresh_token:
            # Use refresh token for sandbox (3-legged flow)
            response = await client.post(
                token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
        else:
            # Use client credentials for production (2-legged flow)
            if self.use_sandbox:
                raise ValueError(
                    "DigiKey Sandbox requires DIGIKEY_REFRESH_TOKEN in .env\n"
                    "Run the authorization script first: python examples/digikey_oauth_authorize.py"
                )
            
            response = await client.post(
                token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
        
        response.raise_for_status()
        token_data = response.json()
        
        # Cache the token (expires in 10 minutes for 2-legged, 30 minutes for 3-legged)
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 600)  # Default 10 minutes
        self._token_expires_at = time.time() + (expires_in - 60)  # 1 minute safety margin
        
        # Update refresh token if provided (3-legged flow)
        new_refresh_token = token_data.get("refresh_token")
        if new_refresh_token:
            print(f"⚠️  New refresh token received. Update your .env:")
            print(f"   DIGIKEY_REFRESH_TOKEN={new_refresh_token}")
        
        return self._access_token
    
    def _get_search_keyword(self, requirements: ComponentRequirements) -> str:
        """Build search keyword from component requirements."""
        keywords = []
        
        # Add component type
        type_map = {
            ComponentType.MOSFET: "MOSFET",
            ComponentType.DIODE: "Diode",
            ComponentType.CAPACITOR: "Capacitor",
            ComponentType.INDUCTOR: "Inductor",
            ComponentType.TRANSFORMER: "Transformer",
            ComponentType.RESISTOR: "Resistor"
        }
        keywords.append(type_map.get(requirements.component_type, ""))
        
        # Add voltage rating if applicable
        if requirements.voltage_max:
            voltage_v = requirements.voltage_max * requirements.voltage_margin
            keywords.append(f"{int(voltage_v)}V")
        
        # Add current rating if applicable
        if requirements.current_max:
            current_a = requirements.current_max * requirements.current_margin
            keywords.append(f"{int(current_a)}A")
        
        return " ".join(keywords)
    
    def _get_filter_params(self, requirements: ComponentRequirements) -> Dict[str, Any]:
        """Build filter parameters from requirements."""
        filters = []
        
        # Voltage filters
        if requirements.voltage_max:
            min_voltage = requirements.voltage_max * requirements.voltage_margin
            filters.append({
                "ParameterId": 252,  # Voltage - Rated
                "MinValue": str(min_voltage)
            })
        
        # Current filters (component-specific)
        if requirements.current_max and requirements.component_type == ComponentType.MOSFET:
            min_current = requirements.current_max * requirements.current_margin
            filters.append({
                "ParameterId": 2088,  # Current - Continuous Drain (Id)
                "MinValue": str(min_current)
            })
        
        return {"Filters": filters} if filters else {}
    
    async def search_components(
        self,
        requirements: ComponentRequirements,
        limit: int = 100
    ) -> List[Component]:
        """
        Search DigiKey catalog for components.
        
        Uses keyword search + filters based on requirements.
        """
        await self._make_request()  # Rate limiting
        
        # Get OAuth2 token
        access_token = await self._get_access_token()
        
        # Build search payload
        keyword = self._get_search_keyword(requirements)
        search_url = f"{self.SANDBOX_SEARCH_URL if self.use_sandbox else self.PRODUCTION_SEARCH_URL}/keyword"
        
        payload = {
            "Keywords": keyword,
            "Limit": min(limit, 50),  # DigiKey max 50 per request
            "Offset": 0,
            "SearchOptions": ["ManufacturerPartSearch"],
            "ExcludeMarketPlaceProducts": True
        }
        
        # Add filters if applicable
        filter_params = self._get_filter_params(requirements)
        if filter_params:
            payload.update(filter_params)
        
        client = await self._get_http_client()
        
        response = await client.post(
            search_url,
            json=payload,
            headers={
                "X-DIGIKEY-Client-Id": self.client_id,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en",
                "X-DIGIKEY-Locale-Currency": "USD"
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Parse response and convert to domain models
        components = []
        for product in data.get("Products", []):
            component = self._parse_product(product)
            if component:
                components.append(component)
        
        return components
    
    async def get_component_details(self, part_number: str) -> Optional[Component]:
        """Get detailed specifications for a specific part number."""
        await self._make_request()  # Rate limiting
        
        # Get OAuth2 token
        access_token = await self._get_access_token()
        
        details_url = (
            self.SANDBOX_DETAILS_URL if self.use_sandbox else self.PRODUCTION_DETAILS_URL
        ).format(part_number=part_number)
        
        client = await self._get_http_client()
        
        response = await client.get(
            details_url,
            headers={
                "X-DIGIKEY-Client-Id": self.client_id,
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en"
            }
        )
        
        response.raise_for_status()
        product = response.json()
        
        return self._parse_product(product)
    
    def _parse_product(self, product: Dict[str, Any]) -> Optional[Component]:
        """Parse DigiKey product JSON to domain Component model."""
        try:
            # Extract common fields
            part_number = product.get("ManufacturerProductNumber", "")
            manufacturer = product.get("Manufacturer", {}).get("Name", "Unknown")
            description = product.get("Description", {}).get("ProductDescription", "")
            
            # Get first product variation for pricing/availability
            variations = product.get("ProductVariations", [])
            if not variations:
                return None
            
            first_variation = variations[0]
            
            # Pricing (get quantity 1 price)
            pricing = first_variation.get("StandardPricing", [])
            price_usd = pricing[0].get("UnitPrice", 0.0) if pricing else 0.0
            
            # Availability
            availability = first_variation.get("QuantityAvailableforPackageType", 0)
            
            # Datasheet
            datasheet_url = product.get("DatasheetUrl")
            
            # Package
            package = first_variation.get("PackageType", {}).get("Name", "Unknown")
            
            # Parse parameters to extract component-specific specs
            parameters = {
                param["ParameterText"]: param.get("ValueText", "")
                for param in product.get("Parameters", [])
            }
            
            # Determine component type and create appropriate model
            category = product.get("Category", {}).get("Name", "").lower()
            
            if "mosfet" in category or "fet" in category:
                return self._create_mosfet(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    parameters, package
                )
            elif "diode" in category:
                return self._create_diode(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    parameters, package
                )
            elif "capacitor" in category:
                return self._create_capacitor(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    parameters, package
                )
            elif "inductor" in category:
                return self._create_inductor(
                    part_number, manufacturer, description,
                    price_usd, availability, datasheet_url,
                    parameters, package
                )
            else:
                # Generic component
                return Component(
                    part_number=part_number,
                    manufacturer=manufacturer,
                    description=description,
                    catalog="digikey",
                    price_usd=price_usd,
                    availability=availability,
                    datasheet_url=datasheet_url
                )
        
        except Exception as e:
            print(f"Error parsing DigiKey product: {e}")
            return None
    
    def _create_mosfet(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        params: Dict[str, str], package: str
    ) -> MOSFET:
        """Create MOSFET from DigiKey parameters."""
        return MOSFET(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="digikey",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            type=params.get("FET Type", "N-Channel"),
            vds_max=self._parse_voltage(params.get("Voltage - Rated", "0V")),
            id_continuous=self._parse_current(params.get("Current - Continuous Drain (Id) @ 25°C", "0A")),
            id_pulsed=0.0,  # Not always available
            rds_on=self._parse_resistance(params.get("Rds On (Max) @ Id, Vgs", "0Ω")),
            vgs_threshold=self._parse_voltage(params.get("Vgs(th) (Max) @ Id", "0V")),
            qg_total=self._parse_charge(params.get("Gate Charge (Qg) (Max) @ Vgs", "0nC")),
            package=package
        )
    
    def _create_diode(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        params: Dict[str, str], package: str
    ) -> Diode:
        """Create Diode from DigiKey parameters."""
        return Diode(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="digikey",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            type=params.get("Diode Type", "Standard"),
            vrrm=self._parse_voltage(params.get("Voltage - DC Reverse (Vr) (Max)", "0V")),
            if_avg=self._parse_current(params.get("Current - Average Rectified (Io)", "0A")),
            vf=self._parse_voltage(params.get("Voltage - Forward (Vf) (Max) @ If", "0V")),
            trr=self._parse_time(params.get("Reverse Recovery Time (trr)", "")),
            package=package
        )
    
    def _create_capacitor(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        params: Dict[str, str], package: str
    ) -> Capacitor:
        """Create Capacitor from DigiKey parameters."""
        return Capacitor(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="digikey",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            capacitance=self._parse_capacitance(params.get("Capacitance", "0F")),
            voltage_rating=self._parse_voltage(params.get("Voltage - Rated", "0V")),
            tolerance=self._parse_tolerance(params.get("Tolerance", "0%")),
            dielectric=params.get("Dielectric Material", "Unknown"),
            esr=self._parse_resistance(params.get("ESR (Equivalent Series Resistance)", "")),
            ripple_current=self._parse_current(params.get("Current - Ripple @ Low Frequency", "")),
            package=package
        )
    
    def _create_inductor(
        self, part_number: str, manufacturer: str, description: str,
        price: float, availability: int, datasheet: Optional[str],
        params: Dict[str, str], package: str
    ) -> Inductor:
        """Create Inductor from DigiKey parameters."""
        return Inductor(
            part_number=part_number,
            manufacturer=manufacturer,
            description=description,
            catalog="digikey",
            price_usd=price,
            availability=availability,
            datasheet_url=datasheet,
            inductance=self._parse_inductance(params.get("Inductance", "0H")),
            current_rating=self._parse_current(params.get("Current Rating (Amps)", "0A")),
            dcr=self._parse_resistance(params.get("DC Resistance (DCR)", "0Ω")),
            saturation_current=self._parse_current(params.get("Current - Saturation", "0A")),
            package=package,
            core_material=params.get("Core Material", None)
        )
    
    # Unit parsing helpers
    def _parse_voltage(self, value: str) -> float:
        """Parse voltage string to float (e.g., '100V' -> 100.0)."""
        try:
            return float(value.replace("V", "").strip())
        except:
            return 0.0
    
    def _parse_current(self, value: str) -> float:
        """Parse current string to float (e.g., '10A' -> 10.0)."""
        try:
            value = value.replace("A", "").strip()
            if "m" in value:  # milliamps
                return float(value.replace("m", "")) / 1000.0
            return float(value)
        except:
            return 0.0
    
    def _parse_resistance(self, value: str) -> Optional[float]:
        """Parse resistance string to float (e.g., '0.044Ω' -> 0.044)."""
        try:
            value = value.replace("Ω", "").replace("Ohm", "").strip()
            if not value or value == "-":
                return None
            if "m" in value:  # milliohms
                return float(value.replace("m", "")) / 1000.0
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
            return float(value)
        except:
            return 0.0
    
    def _parse_tolerance(self, value: str) -> float:
        """Parse tolerance string to float (e.g., '±20%' -> 20.0)."""
        try:
            return float(value.replace("%", "").replace("±", "").strip())
        except:
            return 0.0
    
    def _parse_charge(self, value: str) -> float:
        """Parse charge string to float in nC."""
        try:
            value = value.replace("nC", "").strip()
            return float(value)
        except:
            return 0.0
    
    def _parse_time(self, value: str) -> Optional[float]:
        """Parse time string to float in nanoseconds."""
        try:
            value = value.replace("ns", "").strip()
            if not value or value == "-":
                return None
            return float(value)
        except:
            return None
    
    def get_catalog_name(self) -> str:
        """Return catalog name."""
        return "digikey"
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
