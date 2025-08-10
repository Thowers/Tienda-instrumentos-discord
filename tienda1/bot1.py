import asyncio
import os
from dotenv import load_dotenv
import logging
import discord
from discord.ext import commands
from bson import ObjectId
import pymongo

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    logging.error("🚨 La variable de entorno DISCORD_TOKEN no está definida.")
    exit(1)

logging.basicConfig(level=logging.INFO)

client = pymongo.MongoClient(os.getenv('MONGO'))
db = client[os.getenv('DB')]
agregados_coleccion = db['Agregados']

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

PRODUCTO_ROLES = {
    "Amplificadores_Bajo": 1383693968960917514,
    "Amplificadores_Guitarra": 1383694078155161611,
    "Bajos": 1383694110573203537,
    "Baterias_Acusticas": 1383694139291340801,
    "Baterias_Electronicas": 1383694170819919943,
    "Guitarras_Acusticas": 1383694201257988096,
    "Guitarras_Electricas": 1383694239183011862,
    "Interfaces_Audio": 1383694282510303252,
    "Microfonos": 1383694330593542185,
    "Teclados": 1383694357273640961,
}

COLECCIONES = [
    'AmplificadoresBajos', 
    'AmplificadoresGuitarras', 
    'Bajos',
    'BateriasAcusticas', 
    'BateriasElectricas', 
    'GuitarrasAcusticas',
    'GuitarrasElectricas', 
    'InterfacesAudio', 
    'Microfonos', 
    'Teclados',
]
CANALES = [
    'amplificadores-bajo', 
    'amplificadores-guitarras', 
    'bajos',
    'baterias-electricas', 
    'baterias-acusticas', 
    'guitarras-acusticas',
    'guitarras-electricas', 
    'interfaces-audio', 
    'microfonos', 
    'teclados',
]

carritos = {}

class Carrito:
    def __init__(self):
        self.productos = []

    def agregar_producto(self, producto):
        self.productos.append(producto)

    def resumen(self):
        return "\n".join(f"{p['nombre']} — ${p['precio']}" for p in self.productos)

    def vaciar(self):
        self.productos.clear()

async def eliminar():
    for canal_nombre in CANALES:
        canal = discord.utils.get(bot.get_all_channels(), name=canal_nombre)
        if canal and isinstance(canal, discord.TextChannel):
            async for mensaje in canal.history(limit=None):
                try:
                    await mensaje.delete()
                    await asyncio.sleep(0.5)
                except discord.errors.Forbidden:
                    print(f"No se pudo eliminar el mensaje en {canal.name} debido a permisos insuficientes.")
                except discord.errors.HTTPException:
                    print(f"Error al intentar eliminar el mensaje en {canal.name}.")
    print("Todos los mensajes han sido eliminados.")
    result = agregados_coleccion.delete_many({})
    print(f"Se han eliminado {result.deleted_count} documentos de la colección 'Agregados'.")

async def agregar(interaction: discord.Interaction, producto_id):
    producto = None
    for coleccion in COLECCIONES:
        resultado = db[coleccion].find_one({'_id': ObjectId(producto_id)})
        if resultado:
            producto = resultado
            break
    if not producto:
        await interaction.response.send_message("Producto no encontrado.", ephemeral=True)
        return

    guild = interaction.guild
    member = interaction.user
    channel_name = f"carrito-{member.id}"

    cart_channel = discord.utils.get(guild.text_channels, name=channel_name)

    if not cart_channel:
        category_id = 1383237995901222993
        category = guild.get_channel(category_id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        cart_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)
        view = discord.ui.View()
        view.add_item(EliminarCarrito(member.id))
        await cart_channel.send(f"¡Hola {member.mention}! Este es tu carrito de compras personal.", view=view)

    if interaction.user.id not in carritos:
        carritos[interaction.user.id] = Carrito()
    carritos[interaction.user.id].agregar_producto(producto)

    embed = discord.Embed(
        title=producto['nombre'],
        description=f"Estado: {producto['estado']}",
        color=discord.Color.green()
    )
    if producto.get('imagen', '').startswith('http'):
        embed.set_thumbnail(url=producto['imagen'])
    embed.add_field(name="Precio", value=f"${producto['precio']}", inline=False)
    embed.add_field(name="Más información", value=f"[Descripción]({producto['link']})", inline=False)

    await cart_channel.send(embed=embed)
    await interaction.response.send_message(f"Producto {producto['nombre']} agregado a tu carrito. Revisa el canal {cart_channel.mention}", ephemeral=True)

class SelectorProducto(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Producto_lista())

class EliminarCarrito(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(label="Pagar", style=discord.ButtonStyle.red, custom_id=f"eliminar_carrito_{user_id}")
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("No tienes permiso para eliminar este carrito.", ephemeral=True)
            return

        channel = interaction.channel
        if channel:
            try:
                await interaction.response.send_message("El canal del carrito ha sido eliminado.", ephemeral=True)
                await channel.delete()
                if self.user_id in carritos:

                    del carritos[self.user_id]
            except discord.Forbidden:
                await interaction.response.send_message("No tengo permisos para eliminar este canal.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Ocurrió un error al eliminar el canal: {e}", ephemeral=True)

class AgregarCarrito(discord.ui.Button):
    def __init__(self, producto_id:str):
        super().__init__(label="Agregar al carrito", style=discord.ButtonStyle.green, custom_id=f"agregar_{producto_id}")
        self.producto_id = producto_id

    async def callback(self, interaction: discord.Interaction):
        await agregar(interaction, self.producto_id)

class Producto_lista(discord.ui.Select):
    def __init__(self):
        opciones = [
            discord.SelectOption(label="Amplificadores de Bajo", value="Amplificadores_Bajo"),
            discord.SelectOption(label="Amplificadores de Guitarra", value="Amplificadores_Guitarra"),
            discord.SelectOption(label="Bajos", value="Bajos"),
            discord.SelectOption(label="Baterías Acústicas", value="Baterias_Acusticas"),
            discord.SelectOption(label="Baterías Electrónicas", value="Baterias_Electronicas"),
            discord.SelectOption(label="Guitarras Acústicas", value="Guitarras_Acusticas"),
            discord.SelectOption(label="Guitarras Eléctricas", value="Guitarras_Electricas"),
            discord.SelectOption(label="Interfaces de Audio", value="Interfaces_Audio"),
            discord.SelectOption(label="Micrófonos", value="Microfonos"),
            discord.SelectOption(label="Teclados", value="Teclados"),
        ]
        super().__init__(placeholder="Elige el producto…", min_values=1, max_values=1, options=opciones)

    async def callback(self, interaction: discord.Interaction):
        miembro = interaction.user
        elegido = self.values[0]

        if elegido not in PRODUCTO_ROLES:
            return await interaction.response.send_message(
                "Selección inválida.", ephemeral=True
            )

        rol_nuevo = interaction.guild.get_role(PRODUCTO_ROLES[elegido])
        if not rol_nuevo:
            return await interaction.response.send_message(
                "Rol no encontrado en el servidor.", ephemeral=True
            )

        for role_id in PRODUCTO_ROLES.values():
            rol = interaction.guild.get_role(role_id)
            if rol and rol in miembro.roles:
                await miembro.remove_roles(rol)

        await miembro.add_roles(rol_nuevo)
        await interaction.response.send_message(
            f"✅ Tienes acceso al canal **{rol_nuevo.name}**.", ephemeral=True
        )

async def enviar_productos():
    for coleccion, canal_nombre in zip(COLECCIONES, CANALES):
        canal = discord.utils.get(bot.get_all_channels(), name=canal_nombre)
        if not canal:
            continue

        for dato in db[coleccion].find():
            if agregados_coleccion.find_one({'_id': dato['_id']}):
                continue
            agregados_coleccion.insert_one({'_id': dato['_id'], 'nombre': dato['nombre']})

            estado = "Stock" if dato['estado'] != "Agotado" else "Agotado"
            url = dato.get('imagen', '')
            if url.startswith('//'):
                url = 'https:' + url

            embed = discord.Embed(
                title=dato['nombre'],
                description=f"Estado: {estado}",
                color=discord.Color.blue()
            )
            if url.startswith('http'):
                embed.set_thumbnail(url=url)
            embed.add_field(name="Precio", value=f"${dato['precio']}", inline=False)
            embed.add_field(name="Más información", value=f"[Descripción]({dato['link']})", inline=False)

            view = discord.ui.View()
            view.add_item(AgregarCarrito(str(dato['_id'])))
            await canal.send(embed=embed, view=view)
            await asyncio.sleep(0.2)

@bot.event
async def on_ready():
    logging.info(f'✅ Bot conectado como {bot.user.name}')
    await enviar_productos()
    #await eliminar()

    for guild in bot.guilds:
        canal = discord.utils.get(guild.text_channels, name="principal")
        if canal and canal.permissions_for(guild.me).send_messages:
            try:
                await canal.purge(limit=10)
            except discord.Forbidden:
                pass
            embed = discord.Embed(
                title="Bienvenido a la tienda musical",
                description="Selecciona el tipo de instrumento o equipo al que deseas acceder:",
                color=discord.Color.dark_gold()
            )
            await canal.send(embed=embed, view=SelectorProducto())

if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logging.error("🚨 No se pudo iniciar sesión en Discord. Verifica tu token.")
        exit(1)