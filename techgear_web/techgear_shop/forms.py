"""Validación de formularios antes de enviar datos a FastAPI."""

from decimal import Decimal

from django import forms

# Las categorías describen componentes de escritorio, no equipos completos ni periféricos.
CATEGORIES = (
    ("Procesadores", "Procesadores", "cpu"),
    ("Tarjetas gráficas", "Tarjetas gráficas", "gpu"),
    ("Memorias RAM", "Memorias RAM", "ram"),
    ("Almacenamiento", "Almacenamiento", "ssd"),
    ("Placas madre", "Placas madre", "board"),
    ("Fuentes de alimentación", "Fuentes de alimentación", "power"),
    ("Gabinetes", "Gabinetes", "case"),
    ("Refrigeración", "Refrigeración", "cooling"),
)


class CatalogFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, label="Buscar componente")
    category = forms.ChoiceField(
        required=False,
        choices=[("", "Todos los componentes")]
        + [(value, label) for value, label, _ in CATEGORIES],
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Nombre: A a Z"),
            ("price_asc", "Menor precio"),
            ("price_desc", "Mayor precio"),
        ],
    )


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "tu@correo.com",
                "autofocus": True,
            }
        ),
        error_messages={"invalid": "Escribe un correo electrónico válido."},
    )
    # No recortar espacios: forman parte de la contraseña elegida por la persona.
    password = forms.CharField(
        label="Contraseña",
        max_length=128,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Tu contraseña",
            }
        ),
    )


class DashboardFilterForm(CatalogFilterForm):
    """Filtros de presentación; la API determina qué productos puede leer el rol."""

    state = forms.ChoiceField(
        required=False,
        label="Estado",
        choices=[("", "Todos los estados"), ("active", "Activos"), ("inactive", "Inactivos")],
    )


class ProductForm(forms.Form):
    """Contrato HTML explícito: no se copian campos arbitrarios del formulario a la API."""

    sku = forms.CharField(label="SKU", max_length=100)
    name = forms.CharField(label="Nombre", max_length=200)
    brand = forms.CharField(label="Marca", max_length=100)
    category = forms.ChoiceField(
        label="Categoría", choices=[(value, label) for value, label, _ in CATEGORIES]
    )
    description = forms.CharField(
        label="Descripción", max_length=3000, widget=forms.Textarea(attrs={"rows": 4})
    )
    specifications = forms.CharField(
        label="Especificaciones técnicas",
        max_length=12000,
        widget=forms.Textarea(attrs={"rows": 7, "placeholder": "Socket: AM5\nNúcleos: 6"}),
        help_text="Una característica por línea, con el formato Clave: Valor.",
    )
    price = forms.DecimalField(
        label="Precio en COP",
        min_value=Decimal("0"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    stock = forms.IntegerField(
        label="Existencias",
        min_value=0,
        max_value=9223372036854775807,
        widget=forms.NumberInput(attrs={"step": "1", "min": "0"}),
    )
    image_url = forms.URLField(
        label="URL de imagen",
        max_length=2000,
        widget=forms.URLInput(attrs={"placeholder": "https://…"}),
    )
    active = forms.BooleanField(label="Visible en el catálogo", required=False, initial=True)

    def clean_specifications(self):
        """Convierte líneas a clave/valor y rechaza duplicados para evitar pérdida de datos."""
        result = {}
        seen = set()
        for line in self.cleaned_data["specifications"].splitlines():
            if not line.strip():
                continue
            key, separator, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if not separator or not key or not value:
                raise forms.ValidationError(
                    "Cada línea debe contener una clave y un valor separados por :."
                )
            if key.casefold() in seen:
                raise forms.ValidationError("No repitas el nombre de una característica.")
            seen.add(key.casefold())
            result[key] = value
        if not result:
            raise forms.ValidationError("Incluye al menos una característica técnica.")
        return result

    def payload(self):
        """Conserva Decimal como texto JSON y entrega existencias como entero."""
        values = self.cleaned_data
        return {
            key: str(values[key]) if key == "price" else values[key]
            for key in (
                "sku",
                "name",
                "brand",
                "category",
                "description",
                "specifications",
                "price",
                "stock",
                "image_url",
                "active",
            )
        } | {"currency": "COP"}

    @staticmethod
    def initial_for(product):
        """Traduce el objeto de lectura al formato editable sin redondear importes."""
        return {
            key: getattr(product, key)
            for key in (
                "sku",
                "name",
                "brand",
                "category",
                "description",
                "price",
                "stock",
                "image_url",
                "active",
            )
        } | {
            "specifications": "\n".join(
                f"{key}: {value}" for key, value in product.specifications.items()
            )
        }
