from flask import Flask, render_template, request, redirect, url_for, make_response
import sqlite3
from datetime import datetime, timedelta, date
from functools import wraps

app = Flask(__name__)

# ---------- Conexão com o banco ----------
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# ---------- Inicialização do banco ----------
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS livros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        autor TEXT,
        categoria TEXT,
        quantidade INTEGER DEFAULT 1,
        disponivel INTEGER DEFAULT 1
    )
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pessoas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            contato TEXT,
            data_retirada TEXT,
            hora_retirada TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emprestimos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            livro_id INTEGER,
            pessoa_id INTEGER,
            data_emprestimo TEXT,
            data_devolucao TEXT,
            devolvido INTEGER DEFAULT 0,
            FOREIGN KEY (livro_id) REFERENCES livros(id),
            FOREIGN KEY (pessoa_id) REFERENCES pessoas(id)
        )
    ''')

    conn.commit()
    conn.close()

# ---------- Middleware para não armazenar cache ----------
def no_cache(view):
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return no_cache_view

# ---------- Rota inicial ----------
@app.route('/')
def index():
    return render_template('index.html')

# ---------- Livros ----------
@app.route('/livros', methods=['GET', 'POST'])
def livros():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        autor = request.form['autor']
        categoria = request.form['categoria']
        quantidade = int(request.form.get('quantidade', 1))

        cursor.execute(
            'INSERT INTO livros (titulo, autor, categoria, quantidade, disponivel) VALUES (?, ?, ?, ?, ?)',
            (titulo, autor, categoria, quantidade, 1 if quantidade > 0 else 0)
        )
        conn.commit()
        return redirect('/livros')

    livros = cursor.execute('SELECT * FROM livros').fetchall()
    conn.close()
    return render_template('livros.html', livros=livros)

# ---------- Pessoas (listar e cadastrar) ----------
@app.route('/pessoas', methods=['GET', 'POST'])
@no_cache
def pessoas():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        nome = request.form['nome']
        contato = request.form['contato']
        data_retirada = request.form['data_retirada']
        hora_retirada = request.form['hora_retirada']

        cursor.execute(
            'INSERT INTO pessoas (nome, contato, data_retirada, hora_retirada) VALUES (?, ?, ?, ?)',
            (nome, contato, data_retirada, hora_retirada)
        )
        conn.commit()
        return redirect(url_for('pessoas'))

    pessoas = cursor.execute('SELECT * FROM pessoas ORDER BY nome ASC').fetchall()
    conn.close()
    return render_template('pessoas.html', pessoas=pessoas)

# ---------- Editar Pessoa ----------
@app.route('/pessoas/edit/<int:id>', methods=['GET', 'POST'])
@no_cache
def edit_pessoa(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        nome = request.form['nome']
        contato = request.form['contato']
        data_retirada = request.form['data_retirada']
        hora_retirada = request.form['hora_retirada']

        cursor.execute(
            'UPDATE pessoas SET nome = ?, contato = ?, data_retirada = ?, hora_retirada = ? WHERE id = ?',
            (nome, contato, data_retirada, hora_retirada, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('pessoas'))

    pessoa = cursor.execute('SELECT * FROM pessoas WHERE id = ?', (id,)).fetchone()
    conn.close()

    if pessoa is None:
        return 'Pessoa não encontrada', 404

    return render_template('pessoas_edit.html', pessoa=pessoa)

# ---------- Excluir Pessoa ----------
@app.route('/pessoas/delete/<int:id>', methods=['POST'])
@no_cache
def delete_pessoa(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pessoas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('pessoas'))

# ---------- Empréstimos por Pessoa ----------
@app.route('/pessoas/<int:pessoa_id>/emprestimos')
@no_cache
def emprestimos_por_pessoa(pessoa_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    pessoa = cursor.execute('SELECT * FROM pessoas WHERE id = ?', (pessoa_id,)).fetchone()
    if not pessoa:
        return 'Pessoa não encontrada', 404

    emprestimos = cursor.execute('''
        SELECT e.*, l.titulo FROM emprestimos e
        JOIN livros l ON e.livro_id = l.id
        WHERE e.pessoa_id = ?
    ''', (pessoa_id,)).fetchall()

    conn.close()
    return render_template('emprestimos_por_pessoa.html', pessoa=pessoa, emprestimos=emprestimos)

# ---------- Avisos de Empréstimos ----------
@app.route('/emprestimos/avisos')
def emprestimos_avisos():
    conn = get_db_connection()
    cursor = conn.cursor()

    hoje = datetime.now().date()

    cursor.execute('''
        SELECT e.*, l.titulo, p.nome 
        FROM emprestimos e
        JOIN livros l ON e.livro_id = l.id
        JOIN pessoas p ON e.pessoa_id = p.id
        WHERE e.devolvido = 0
    ''')
    emprestimos = cursor.fetchall()
    conn.close()

    avisos = []
    for emp in emprestimos:
        data_devolucao = datetime.strptime(emp['data_devolucao'], '%Y-%m-%d').date()
        dias_para_devolucao = (data_devolucao - hoje).days
        if dias_para_devolucao < 0:
            status = 'atrasado'
        elif dias_para_devolucao <= 5:
            status = 'vencendo'
        else:
            status = None
        
        if status:
            avisos.append({
                'id': emp['id'],
                'titulo': emp['titulo'],
                'nome': emp['nome'],
                'data_devolucao': emp['data_devolucao'],
                'status': status,
                'dias_para_devolucao': dias_para_devolucao
            })

    return render_template('avisos_emprestimos.html', avisos=avisos)

# ---------- Renovar Empréstimo ----------
@app.route('/emprestimos/<int:emprestimo_id>/renovar', methods=['POST'])
def renovar_emprestimo(emprestimo_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM emprestimos WHERE id = ?', (emprestimo_id,))
    emprestimo = cursor.fetchone()
    if not emprestimo:
        conn.close()
        return "Empréstimo não encontrado", 404

    if emprestimo['devolvido'] == 1:
        conn.close()
        return "Empréstimo já devolvido", 400

    hoje = datetime.now().date()
    ultima_data = datetime.strptime(emprestimo['data_devolucao'], '%Y-%m-%d').date()
    nova_data = max(hoje, ultima_data) + timedelta(days=5)

    cursor.execute('UPDATE emprestimos SET data_devolucao = ? WHERE id = ?', (nova_data.strftime('%Y-%m-%d'), emprestimo_id))
    conn.commit()
    conn.close()
    return redirect(url_for('emprestimos_avisos'))

# ---------- Garante coluna quantidade ----------
conn = sqlite3.connect('database.db')
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE livros ADD COLUMN quantidade INTEGER DEFAULT 1;")
except Exception as e:
    print(e)
conn.commit()
conn.close()
print("Coluna quantidade garantida!")

# ---------- Empréstimos ----------
@app.route('/emprestimos', methods=['GET', 'POST'])
def emprestimos():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        pessoa_id = request.form['pessoa_id']
        livro_id = request.form['livro_id']
        data_emprestimo = request.form['data_emprestimo']
        data_devolucao = request.form['data_devolucao']

        # Cria o empréstimo
        cursor.execute('''
            INSERT INTO emprestimos (livro_id, pessoa_id, data_emprestimo, data_devolucao, devolvido)
            VALUES (?, ?, ?, ?, 0)
        ''', (livro_id, pessoa_id, data_emprestimo, data_devolucao))

        # Diminui o estoque do livro
        cursor.execute('UPDATE livros SET quantidade = quantidade - 1 WHERE id = ? AND quantidade > 0', (livro_id,))
        # Atualiza disponibilidade
        cursor.execute('UPDATE livros SET disponivel = CASE WHEN quantidade > 0 THEN 1 ELSE 0 END WHERE id = ?', (livro_id,))
        conn.commit()
        return redirect(url_for('emprestimos'))

    # Listar empréstimos
    emprestimos = cursor.execute('''
        SELECT e.*, p.nome as pessoa_nome, l.titulo as livro_titulo
        FROM emprestimos e
        JOIN pessoas p ON e.pessoa_id = p.id
        JOIN livros l ON e.livro_id = l.id
        ORDER BY e.data_emprestimo DESC
    ''').fetchall()

    # Adiciona o campo 'atrasado' para cada empréstimo
    emprestimos_list = []
    for emp in emprestimos:
        emp_dict = dict(emp)
        if not emp_dict['devolvido']:
            emp_dict['atrasado'] = date.today().isoformat() > emp_dict['data_devolucao']
        else:
            emp_dict['atrasado'] = False
        emprestimos_list.append(emp_dict)

    # Só livros disponíveis
    livros = cursor.execute('SELECT * FROM livros WHERE quantidade > 0').fetchall()
    pessoas = cursor.execute('SELECT * FROM pessoas').fetchall()
    conn.close()
    return render_template('emprestimos.html', emprestimos=emprestimos_list, livros=livros, pessoas=pessoas)

# ---------- Devolver Empréstimo ----------
@app.route('/emprestimos/<int:emprestimo_id>/devolver', methods=['POST'])
def devolver_emprestimo(emprestimo_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Marca o empréstimo como devolvido
    cursor.execute('UPDATE emprestimos SET devolvido = 1 WHERE id = ?', (emprestimo_id,))
    # Recupera o livro relacionado
    cursor.execute('SELECT livro_id FROM emprestimos WHERE id = ?', (emprestimo_id,))
    livro = cursor.fetchone()
    if livro:
        # Aumenta o estoque do livro
        cursor.execute('UPDATE livros SET quantidade = quantidade + 1 WHERE id = ?', (livro['livro_id'],))
        # Atualiza disponibilidade
        cursor.execute('UPDATE livros SET disponivel = 1 WHERE id = ?', (livro['livro_id'],))
    conn.commit()
    conn.close()
    return redirect(url_for('emprestimos'))

# ---------- Excluir Livro ----------
@app.route('/livros/delete/<int:id>', methods=['POST'])
def delete_livro(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM livros WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('livros'))

# ---------- Editar Livro ----------
@app.route('/livros/edit/<int:id>', methods=['GET', 'POST'])
def edit_livro(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        titulo = request.form['titulo']
        autor = request.form['autor']
        categoria = request.form['categoria']
        quantidade = int(request.form['quantidade'])
        cursor.execute(
            'UPDATE livros SET titulo = ?, autor = ?, categoria = ?, quantidade = ?, disponivel = ? WHERE id = ?',
            (titulo, autor, categoria, quantidade, 1 if quantidade > 0 else 0, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('livros'))
    livro = cursor.execute('SELECT * FROM livros WHERE id = ?', (id,)).fetchone()
    conn.close()
    if livro is None:
        return 'Livro não encontrado', 404
    return render_template('livros_edit.html', livro=livro)

# ---------- Inicialização ----------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)