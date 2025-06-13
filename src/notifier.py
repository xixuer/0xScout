import smtplib
import markdown2
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger import LOG
import socket # From previous step
import traceback # From previous step
import os # For template path

class Notifier:
    def __init__(self, email_settings):
        self.email_settings = email_settings
        # Define template path relative to this file
        # Ensure the 'templates' directory is at the same level as 'notifier.py' or adjust path accordingly.
        # Assuming 'src/templates/email_template.html' and 'src/notifier.py'
        self.template_path = os.path.join(os.path.dirname(__file__), 'templates', 'email_template.html')
        
    def _generate_toc(self, markdown_text):
        """从Markdown文本生成目录HTML"""
        # 查找所有标题行
        headers = []
        for line in markdown_text.split('\n'):
            if line.startswith('#'):
                level = 0
                for char in line:
                    if char == '#':
                        level += 1
                    else:
                        break
                
                if level > 0 and level <= 3:  # 只处理一级到三级标题
                    title = line.lstrip('#').strip()
                    anchor = title.lower().replace(' ', '-').replace('.', '').replace(':', '')
                    anchor = re.sub(r'[^\w\-]', '', anchor)
                    # 中文处理
                    anchor = re.sub(r'[\u4e00-\u9fff]', lambda x: f"ch{ord(x.group())}", anchor)
                    headers.append((level, title, anchor))
        
        if not headers:
            return ""  # 如果没有找到标题，则返回空字符串
        
        # 生成目录HTML
        toc_html = '<div class="toc">\n'
        toc_html += '<div class="toc-title">目录</div>\n'
        toc_html += '<ul>\n'
        
        current_level = 0
        for level, title, anchor in headers:
            # 根据标题层级调整缩进
            if level > current_level:
                while level > current_level:
                    toc_html += '<ul>\n'
                    current_level += 1
            elif level < current_level:
                while level < current_level:
                    toc_html += '</ul>\n'
                    current_level -= 1
            
            toc_html += f'<li><a href="#{anchor}">{title}</a></li>\n'
        
        # 关闭所有剩余的列表标签
        while current_level > 0:
            toc_html += '</ul>\n'
            current_level -= 1
        
        toc_html += '</ul>\n'
        toc_html += '</div>\n'
        
        return toc_html

    def _load_email_template(self, subject_content, report_html_content):
        try:
            # Check if template file exists
            if not os.path.exists(self.template_path):
                LOG.error(f"Email template file not found at {self.template_path}. Sending plain HTML report.")
                # Fallback to just the report HTML if template is missing
                return f"<h1>{subject_content}</h1>{report_html_content}"

            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            template = template.replace('{{subject}}', subject_content)
            template = template.replace('{{report_content}}', report_html_content)
            return template
        except FileNotFoundError: # Should be caught by os.path.exists, but as a safeguard
            LOG.error(f"Email template not found (FileNotFoundError) at {self.template_path}. Sending plain HTML report.")
            return f"<h1>{subject_content}</h1>{report_html_content}"
        except Exception as e:
            LOG.error(f"Error loading email template: {e}. Sending plain HTML report.")
            return f"<h1>{subject_content}</h1>{report_html_content}"
    
    def _preprocess_markdown(self, markdown_text):
        """
        预处理Markdown文本，增强一些特性的支持
        """
        # 修复列表项的识别 (确保列表项前有空行)
        pattern = r'([^\n])\n([\s]*[-*+][\s]+)'
        markdown_text = re.sub(pattern, r'\1\n\n\2', markdown_text)
        
        # 修复数字列表项的识别
        pattern = r'([^\n])\n([\s]*\d+\.[\s]+)'
        markdown_text = re.sub(pattern, r'\1\n\n\2', markdown_text)
        
        # 增强代码块的处理
        def enhance_code_blocks(match):
            entire_block = match.group(0)
            code_content = match.group(1)
            
            # 检查是否有语言标识
            first_line = code_content.strip().split('\n')[0] if '\n' in code_content.strip() else ''
            language = ''
            
            if first_line and not first_line.startswith(' '):
                language = first_line
                # 移除语言标识行
                code_content = code_content[len(first_line):].strip()
                return f"```{language}\n{code_content}\n```"
            
            return entire_block
        
        # 处理以```开始和结束的代码块
        pattern = r'```(.*?)```'
        markdown_text = re.sub(pattern, enhance_code_blocks, markdown_text, flags=re.DOTALL)
        
        # 为标题添加锚点ID
        lines = markdown_text.split('\n')
        for i in range(len(lines)):
            if lines[i].startswith('#'):
                level = 0
                for char in lines[i]:
                    if char == '#':
                        level += 1
                    else:
                        break
                
                if level > 0:
                    title = lines[i].lstrip('#').strip()
                    anchor = title.lower().replace(' ', '-').replace('.', '').replace(':', '')
                    anchor = re.sub(r'[^\w\-]', '', anchor)
                    # 中文处理
                    anchor = re.sub(r'[\u4e00-\u9fff]', lambda x: f"ch{ord(x.group())}", anchor)
                    
                    lines[i] = f"{lines[i]} {{#{anchor}}}"
        
        markdown_text = '\n'.join(lines)
        
        # 在大块内容之间添加"回到顶部"链接
        if len(markdown_text) > 1000:  # 只对较长内容添加
            headers = re.findall(r'^#{2,3} .+$', markdown_text, re.MULTILINE)
            if len(headers) >= 2:  # 至少有两个二级或三级标题
                # 在二级和三级标题前添加"回到顶部"链接
                markdown_text = re.sub(
                    r'(\n{2,})^(#{2,3} .+)$',
                    r'\1<div class="back-to-top"><a href="#top">回到顶部 ↑</a></div>\n\n\2',
                    markdown_text,
                    flags=re.MULTILINE
                )
        
        return markdown_text
    
    def _enhance_html_with_toc(self, html_content, markdown_text):
        """在HTML内容的开头添加目录"""
        toc_html = self._generate_toc(markdown_text)
        if toc_html:
            # 添加top锚点
            html_content = f'<a id="top"></a>\n{toc_html}\n{html_content}'
        
        return html_content

    def notify_github_report(self, repo, report):
        if self.email_settings:
            subject = f"[GitHub] {repo} 进展简报"
            self.send_email(subject, report)
        else:
            LOG.warning("邮件设置未配置正确，无法发送 GitHub 报告通知")

    def notify_hn_report(self, date, report):
        if self.email_settings:
            subject = f"[HackerNews] {date} 技术趋势"
            self.send_email(subject, report)
        else:
            LOG.warning("邮件设置未配置正确，无法发送 Hacker News 报告通知")

    def send_email(self, subject, report_markdown):
        LOG.info(f"准备发送邮件: {subject}")

        if not self.email_settings.get('from') or \
           not self.email_settings.get('to') or \
           not self.email_settings.get('smtp_server') or \
           not self.email_settings.get('smtp_port'):
            LOG.error("Email settings incomplete (from, to, server, or port missing). Cannot send email.")
            return

        msg = MIMEMultipart('alternative')
        msg['From'] = self.email_settings['from']

        recipients = self.email_settings['to']
        if isinstance(recipients, list):
            msg['To'] = ", ".join(recipients)
        else: # Assuming it's a string for a single recipient
            msg['To'] = recipients
            recipients = [recipients] # server.sendmail expects a list

        if not recipients: # Handle empty recipient list after processing
            LOG.error("No recipients configured for email. Cannot send.")
            return

        msg['Subject'] = subject

        # 预处理Markdown内容
        processed_markdown = self._preprocess_markdown(report_markdown)

        # 使用markdown2的扩展功能，支持更多的Markdown特性
        extras = [
            "code-friendly",   # 保留代码块中的空格
            "fenced-code-blocks", # 支持```代码块
            "tables",          # 支持表格
            "break-on-newline", # 处理换行
            "header-ids",      # 为标题生成IDs
            "numbering",       # 支持数字列表
            "strike",          # 支持删除线
            "task_list",       # 支持任务列表
            "wiki-tables",      # 支持更复杂的表格
            "code-color"       # 支持代码块语法高亮
        ]
        
        # 转换Markdown为HTML
        html_report_content = markdown2.markdown(processed_markdown, extras=extras)
        
        # 添加目录
        if len(report_markdown) > 800:  # 只对长内容添加目录
            html_report_content = self._enhance_html_with_toc(html_report_content, processed_markdown)
        
        # 添加纯文本版本作为备用显示
        plain_text = report_markdown
        msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        
        # 使用自定义模板生成美观的HTML邮件
        final_html_body = self._load_email_template(subject, html_report_content)
        msg.attach(MIMEText(final_html_body, 'html', 'utf-8'))

        smtp_server_addr = self.email_settings['smtp_server']
        smtp_port = int(self.email_settings['smtp_port'])
        sender_email = msg['From']
        password = self.email_settings.get('password', '') # Use .get for password

        server = None # Initialize server to None for finally block
        try:
            LOG.info(f"Attempting to send email via {smtp_server_addr}:{smtp_port}")
            LOG.debug(f"From: {sender_email}, To: {recipients}, Subject: {subject}")

            if smtp_port == 587:
                LOG.info(f"Using SMTP (STARTTLS) on port {smtp_port}")
                server = smtplib.SMTP(smtp_server_addr, smtp_port, timeout=10)
                server.ehlo()
                server.starttls()
                server.ehlo()
            elif smtp_port == 465:
                LOG.info(f"Using SMTP_SSL on port {smtp_port}")
                server = smtplib.SMTP_SSL(smtp_server_addr, smtp_port, timeout=10)
            else:
                LOG.warning(f"Uncommon SMTP port {smtp_port} configured. Attempting SMTP_SSL as default.")
                server = smtplib.SMTP_SSL(smtp_server_addr, smtp_port, timeout=10)

            if password: # Only login if password is provided
                LOG.debug(f"Logging in with username: {sender_email}")
                server.login(sender_email, password)
            else:
                LOG.info("No password configured. Attempting to send without SMTP authentication.")

            LOG.debug(f"Sending email to: {recipients}")
            server.sendmail(sender_email, recipients, msg.as_string())
            LOG.info("邮件发送成功！")

        except smtplib.SMTPAuthenticationError as e:
            LOG.error(f"SMTP Authentication Error for {sender_email} on {smtp_server_addr}:{smtp_port}. Error: {str(e)}. Check email, password/token.")
        except smtplib.SMTPServerDisconnected as e:
            LOG.error(f"SMTP Server Disconnected: {str(e)} for {smtp_server_addr}:{smtp_port}.")
        except smtplib.SMTPConnectError as e:
            LOG.error(f"SMTP Connect Error: {str(e)}. Failed to connect to {smtp_server_addr}:{smtp_port}.")
        except socket.gaierror as e:
            LOG.error(f"Socket/DNS Error: {str(e)}. Ensure '{smtp_server_addr}' is correct.")
        except socket.timeout:
            LOG.error(f"SMTP connection timed out for {smtp_server_addr}:{smtp_port}.")
        except Exception as e:
            LOG.error(f"发送邮件失败 (General Exception for {smtp_server_addr}:{smtp_port}): {str(e)}")
            LOG.error(traceback.format_exc())
        finally:
            if server:
                try:
                    server.quit()
                except smtplib.SMTPServerDisconnected:
                    # Server might have already disconnected if there was an issue.
                    pass
                except Exception as e:
                    LOG.warning(f"Error during server.quit(): {e}")

if __name__ == '__main__':
    from config import Config
    config = Config()
    notifier = Notifier(config.email)

    # 测试 GitHub 报告邮件通知
    test_repo = "DjangoPeng/openai-quickstart"
    test_report = """
# DjangoPeng/openai-quickstart 项目进展

## 时间周期：2024-08-24

## 新增功能
- Assistants API 代码与文档

## 主要改进
- 适配 LangChain 新版本

## 修复问题
- 关闭了一些未解决的问题。

```python
def hello_world():
    print("Hello, World!")
```
"""
    notifier.notify_github_report(test_repo, test_report)

    # 测试 Hacker News 报告邮件通知
    hn_report = """
# Hacker News 前沿技术趋势 (2024-09-01)

## Top 1：硬盘驱动器的讨论引发热门讨论

关于硬盘驱动器的多个讨论，尤其是关于未使用和不需要的硬盘驱动器的文章，显示出人们对科技过时技术的兴趣。

详细内容见相关链接：

- http://tom7.org/harder/
- http://tom7.org/harder/

## Top 2：学习 Linux 的重要性和 Bubbletea 程序开发

有关于 Linux 的讨论，强调了 Linux 在现代开发中的重要性和应用性，以及关于构建 Bubbletea 程序的讨论，展示了 Bubbletea 在开发中的应用性和可能性。

详细内容见相关链接：

- https://opiero.medium.com/why-you-should-learn-linux-9ceace168e5c
- https://leg100.github.io/en/posts/building-bubbletea-programs/

## Top 3：Nvidia 在 AI 领域中的强大竞争力

有关于 Nvidia 的四个未知客户，每个人购买价值超过 3 亿美元的讨论，显示出 N 维达在 AI 领域中的强大竞争力。

详细内容见相关链接：

- https://fortune.com/2024/08/29/nvidia-jensen-huang-ai-customers/

"""
    notifier.notify_hn_report("2024-09-01", hn_report)
