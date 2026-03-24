package broker;

import javax.swing.*;
import javax.swing.border.LineBorder;
import java.awt.*;
import java.util.*;

public class BrokerDashboard {
    private final BrokerRemote service;
    private JFrame frame;
    private JPanel gridPanel;
    private JLabel infoLabel;
    private final Map<String, SaleRow> saleRows = new LinkedHashMap<>();

    private static final Color COLOR_BG = new Color(10, 14, 39);
    private static final Color COLOR_GRAY = new Color(141, 141, 141);
    private static final Color COLOR_GREEN = new Color(43, 191, 106);
    private static final Color COLOR_YELLOW = new Color(242, 196, 45);
    private static final Color COLOR_ORANGE = new Color(242, 139, 37);
    private static final Color COLOR_RED = new Color(208, 49, 45);
    private static final Color COLOR_PROGRESS = new Color(43, 191, 106);

    private static final int ROW_HEIGHT = 77;
    private static final int SERVER_WIDTH = 184;
    private static final int STATUS_WIDTH = 168;
    private static final int CLIENT_WIDTH = 136;
    private static final int PROGRESS_WIDTH = 304;

    public BrokerDashboard(BrokerRemote service) {
        this.service = service;
    }

    public void show() {
        SwingUtilities.invokeLater(() -> {
            frame = new JFrame("Broker RMI - Estados de venta");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setSize(1200, 576);
            frame.setLocationRelativeTo(null);

            gridPanel = new JPanel();
            gridPanel.setBackground(COLOR_BG);
            gridPanel.setLayout(new BoxLayout(gridPanel, BoxLayout.Y_AXIS));

            infoLabel = new JLabel("Esperando eventos del broker...");
            infoLabel.setForeground(Color.WHITE);
            infoLabel.setFont(new Font("Arial", Font.BOLD, 19));
            infoLabel.setBorder(BorderFactory.createEmptyBorder(12, 14, 12, 14));
            infoLabel.setOpaque(true);
            infoLabel.setBackground(COLOR_BG);

            JScrollPane scrollPane = new JScrollPane(gridPanel);
            scrollPane.getViewport().setBackground(COLOR_BG);
            scrollPane.setBackground(COLOR_BG);

            frame.setLayout(new BorderLayout());
            frame.add(infoLabel, BorderLayout.NORTH);
            frame.add(scrollPane, BorderLayout.CENTER);
            frame.setVisible(true);

            javax.swing.Timer timer = new javax.swing.Timer(120, e -> refresh());
            timer.start();
        });
    }

    private Color statusToColor(SaleStatus sale) {
        String status = sale.status == null ? "" : sale.status;
        if ("red".equals(status)) {
            return COLOR_RED;
        }
        if ("orange".equals(status)) {
            return COLOR_ORANGE;
        }
        if ("blue".equals(status)) {
            if (sale.expectedClients > 0 && sale.connectedClients < sale.expectedClients) {
                return COLOR_YELLOW;
            }
            return COLOR_GREEN;
        }
        return COLOR_GRAY;
    }

    private String statusToLabel(SaleStatus sale) {
        String status = sale.status == null ? "" : sale.status;
        if ("red".equals(status)) {
            return "Finalizado";
        }
        if ("orange".equals(status)) {
            return "Venta en curso";
        }
        if ("blue".equals(status)) {
            if (sale.expectedClients > 0 && sale.connectedClients < sale.expectedClients) {
                return "Esperando clientes";
            }
            return "Conectado";
        }
        return "Sin eventos";
    }

    private void refresh() {
        SwingUtilities.invokeLater(() -> {
            try {
                BrokerSnapshot snapshot = service.getSnapshot();

                for (SaleStatus sale : snapshot.sales) {
                    if (!saleRows.containsKey(sale.saleId)) {
                        SaleRow row = new SaleRow(sale);
                        saleRows.put(sale.saleId, row);
                        gridPanel.add(row.getPanel());
                    }
                    saleRows.get(sale.saleId).update(sale);
                }

                infoLabel.setText("Ventas monitoreadas: " + snapshot.sales.size() + " | Refresco: 120 ms");

                gridPanel.revalidate();
                gridPanel.repaint();
            } catch (Exception ignored) {
                // Ignore RMI errors
            }
        });
    }

    private class SaleRow {
        private final JPanel panel;
        private final JPanel statusPanel;
        private final JLabel statusLabel;
        private final JPanel clientsPanel;
        private final Map<Integer, JPanel> clientCells = new HashMap<>();
        private final JProgressBar soldProgressBar;
        private final JLabel soldProgressText;

        SaleRow(SaleStatus sale) {
            panel = new JPanel();
            panel.setLayout(new BoxLayout(panel, BoxLayout.X_AXIS));
            panel.setBackground(COLOR_BG);
            panel.setMaximumSize(new Dimension(Integer.MAX_VALUE, ROW_HEIGHT + 20));
            panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

            // Panel del servidor (Sale ID)
            JPanel serverPanel = new JPanel();
            serverPanel.setLayout(new BorderLayout());
            serverPanel.setBackground(COLOR_GRAY);
            serverPanel.setPreferredSize(new Dimension(SERVER_WIDTH, ROW_HEIGHT));
            serverPanel.setMaximumSize(new Dimension(SERVER_WIDTH, ROW_HEIGHT));
            serverPanel.setMinimumSize(new Dimension(SERVER_WIDTH, ROW_HEIGHT));

            JLabel serverLabel = new JLabel(sale.saleId);
            serverLabel.setForeground(Color.WHITE);
            serverLabel.setFont(new Font("Arial", Font.BOLD, 19));
            serverLabel.setHorizontalAlignment(JLabel.CENTER);
            serverLabel.setVerticalAlignment(JLabel.CENTER);
            serverPanel.add(serverLabel, BorderLayout.CENTER);
            panel.add(serverPanel);
            panel.add(Box.createHorizontalStrut(8));

            // Panel de estado
            statusPanel = new JPanel();
            statusPanel.setLayout(new BorderLayout());
            statusPanel.setBackground(COLOR_GRAY);
            statusPanel.setPreferredSize(new Dimension(STATUS_WIDTH, ROW_HEIGHT));
            statusPanel.setMaximumSize(new Dimension(STATUS_WIDTH, ROW_HEIGHT));
            statusPanel.setMinimumSize(new Dimension(STATUS_WIDTH, ROW_HEIGHT));

            statusLabel = new JLabel("Sin eventos");
            statusLabel.setForeground(Color.WHITE);
            statusLabel.setFont(new Font("Arial", Font.BOLD, 17));
            statusLabel.setHorizontalAlignment(JLabel.CENTER);
            statusLabel.setVerticalAlignment(JLabel.CENTER);
            statusPanel.add(statusLabel, BorderLayout.CENTER);
            panel.add(statusPanel);
            panel.add(Box.createHorizontalStrut(8));

            // Panel de clientes
            clientsPanel = new JPanel();
            clientsPanel.setLayout(new FlowLayout(FlowLayout.LEFT, 3, 0));
            clientsPanel.setBackground(COLOR_BG);
            panel.add(clientsPanel);

            panel.add(Box.createHorizontalStrut(8));

            JPanel progressPanel = new JPanel();
            progressPanel.setLayout(new BorderLayout(0, 8));
            progressPanel.setBackground(COLOR_BG);
            progressPanel.setPreferredSize(new Dimension(PROGRESS_WIDTH, ROW_HEIGHT));
            progressPanel.setMaximumSize(new Dimension(PROGRESS_WIDTH, ROW_HEIGHT));
            progressPanel.setMinimumSize(new Dimension(PROGRESS_WIDTH, ROW_HEIGHT));

            soldProgressText = new JLabel("0/0 asientos (0%)");
            soldProgressText.setForeground(Color.WHITE);
            soldProgressText.setFont(new Font("Arial", Font.BOLD, 16));

            soldProgressBar = new JProgressBar(0, 100);
            soldProgressBar.setValue(0);
            soldProgressBar.setStringPainted(true);
            soldProgressBar.setString("0%");
            soldProgressBar.setFont(new Font("Arial", Font.BOLD, 14));
            soldProgressBar.setForeground(COLOR_PROGRESS);
            soldProgressBar.setBackground(new Color(45, 49, 80));
            soldProgressBar.setPreferredSize(new Dimension(PROGRESS_WIDTH, 27));

            progressPanel.add(soldProgressText, BorderLayout.NORTH);
            progressPanel.add(soldProgressBar, BorderLayout.CENTER);
            panel.add(progressPanel);
        }

        void update(SaleStatus sale) {
            statusLabel.setText(statusToLabel(sale));
            statusPanel.setBackground(statusToColor(sale));

            // Actualizar o crear celdas de clientes
            int expectedClients = sale.expectedClients;
            int connectedClients = sale.connectedClients;

            for (int i = 0; i < expectedClients; i++) {
                if (!clientCells.containsKey(i)) {
                    JPanel clientCell = new JPanel();
                    clientCell.setLayout(new BorderLayout());
                    clientCell.setBorder(new LineBorder(new Color(100, 100, 100), 1));
                    clientCell.setPreferredSize(new Dimension(CLIENT_WIDTH, ROW_HEIGHT));

                    JLabel label = new JLabel("C" + (i + 1));
                    label.setFont(new Font("Arial", Font.BOLD, 17));
                    label.setHorizontalAlignment(JLabel.CENTER);
                    label.setVerticalAlignment(JLabel.CENTER);
                    label.setForeground(Color.WHITE);
                    clientCell.add(label, BorderLayout.CENTER);

                    clientCells.put(i, clientCell);
                    clientsPanel.add(clientCell);
                }

                JPanel cell = clientCells.get(i);
                cell.setBackground(i < connectedClients ? COLOR_GREEN : COLOR_GRAY);
            }

            int sold = Math.max(0, sale.soldSeats);
            int total = Math.max(0, sale.totalSeats);
            int percent = total > 0 ? Math.min(100, (int) Math.round((sold * 100.0) / total)) : 0;

            soldProgressText.setText(sold + "/" + total + " asientos (" + percent + "%)");
            soldProgressBar.setValue(percent);
            soldProgressBar.setString(percent + "%");
        }

        JPanel getPanel() {
            return panel;
        }
    }
}
